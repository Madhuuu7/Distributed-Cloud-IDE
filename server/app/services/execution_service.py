"""Runs untrusted user code in a throwaway, locked-down Docker container.

Each submission gets a fresh container that is created, fed the code, run under
hard resource limits, and destroyed. The container has no network, a read-only
root filesystem, no Linux capabilities, a memory/CPU/PID ceiling, and runs as
an unprivileged user.

Setting EXECUTION_BACKEND=local swaps in a bare subprocess on this host. That
path has none of the isolation above and exists only for local development on
machines without a Docker daemon.
"""

import io
import logging
import os
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass

from app.core.config import (
    EXECUTION_BACKEND,
    EXECUTION_CPU_LIMIT,
    EXECUTION_MAX_OUTPUT_BYTES,
    EXECUTION_MEMORY_LIMIT,
    EXECUTION_PIDS_LIMIT,
    EXECUTION_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

SANDBOX_DIR = "sandbox"
TRUNCATION_NOTICE = "\n... output truncated ..."

DISABLED_MESSAGE = (
    "Code execution is switched off on this deployment. The host provides no "
    "Docker daemon, and running user code without one would mean running it "
    "unsandboxed on the server. Clone and run the project locally to use this "
    "feature."
)


class ExecutionError(Exception):
    """Base class for execution failures that should surface to the caller."""


class UnsupportedLanguage(ExecutionError):
    pass


class SandboxUnavailable(ExecutionError):
    pass


@dataclass(frozen=True)
class RuntimeSpec:
    image: str
    filename: str
    command: list[str]
    local_command: list[str]


RUNTIMES: dict[str, RuntimeSpec] = {
    "python": RuntimeSpec(
        image="python:3.12-slim",
        filename="main.py",
        # -I isolates the interpreter, -B skips writing .pyc to a read-only fs.
        command=["python", "-I", "-B", "main.py"],
        local_command=["python", "-I", "-B"],
    ),
    "javascript": RuntimeSpec(
        image="node:20-alpine",
        filename="main.js",
        command=["node", "main.js"],
        local_command=["node"],
    ),
}


@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int | None
    duration_ms: int
    timed_out: bool
    backend: str


def supported_languages() -> list[str]:
    return sorted(RUNTIMES)


def run_code(language: str, code: str) -> ExecutionResult:
    spec = RUNTIMES.get(language.strip().lower())

    if spec is None:
        supported = ", ".join(supported_languages())
        raise UnsupportedLanguage(
            f"Unsupported language '{language}'. Supported: {supported}."
        )

    if EXECUTION_BACKEND == "disabled":
        raise SandboxUnavailable(DISABLED_MESSAGE)

    if EXECUTION_BACKEND == "local":
        logger.warning("Executing user code with the unsandboxed local backend")
        return _run_locally(spec, code)

    return _run_in_docker(spec, code)


# The sandbox has no network, so nothing can be pip-installed into it and
# pytest is not in the base image. `unittest discover` ships with the standard
# library and writes nothing to disk, which is what a read-only root filesystem
# requires.
DEFAULT_TEST_COMMANDS: dict[str, list[str]] = {
    "python": ["python", "-I", "-B", "-m", "unittest", "discover", "-s", ".", "-p", "test*.py"],
    "javascript": ["node", "--test"],
}


def default_test_command(language: str) -> list[str] | None:
    return DEFAULT_TEST_COMMANDS.get(language.strip().lower())


def run_project(
    language: str,
    files: dict[str, str],
    command: list[str] | None = None,
) -> ExecutionResult:
    """Run a whole project under the same isolation as a single submission.

    Used by the agentic fix loop, where the question is whether a set of files
    passes its tests rather than what one script prints.
    """
    spec = RUNTIMES.get(language.strip().lower())

    if spec is None:
        supported = ", ".join(supported_languages())
        raise UnsupportedLanguage(
            f"Unsupported language '{language}'. Supported: {supported}."
        )

    resolved = command or default_test_command(language) or spec.command

    if EXECUTION_BACKEND == "disabled":
        raise SandboxUnavailable(DISABLED_MESSAGE)

    if EXECUTION_BACKEND == "local":
        logger.warning("Running project with the unsandboxed local backend")

        return _run_locally(spec, "", files=files, command=resolved)

    return _run_in_docker(spec, "", files=files, command=resolved)


def _truncate(raw: bytes) -> str:
    if len(raw) > EXECUTION_MAX_OUTPUT_BYTES:
        head = raw[:EXECUTION_MAX_OUTPUT_BYTES].decode("utf-8", "replace")
        return head + TRUNCATION_NOTICE

    return raw.decode("utf-8", "replace")


def _build_code_archive(filename: str, code: str) -> bytes:
    """Tar the submission so it can be copied into the container before start."""
    return _build_archive({filename: code})


def _build_archive(files: dict[str, str]) -> bytes:
    """Tar a set of files so they can be copied in before the container starts.

    Every file is mode 0444 inside a 0555 directory. Combined with the
    read-only root filesystem this means the running code cannot rewrite its
    own source - which matters for the fix loop, where the whole question being
    asked is whether *this exact* code passes.
    """
    buffer = io.BytesIO()

    with tarfile.open(fileobj=buffer, mode="w") as tar:
        directory = tarfile.TarInfo(SANDBOX_DIR)
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o555
        tar.addfile(directory)

        for name, content in files.items():
            safe_name = _safe_member_name(name)
            data = content.encode("utf-8")

            member = tarfile.TarInfo(f"{SANDBOX_DIR}/{safe_name}")
            member.size = len(data)
            member.mode = 0o444
            tar.addfile(member, io.BytesIO(data))

    return buffer.getvalue()


def _safe_member_name(name: str) -> str:
    """Flatten a path so a crafted filename cannot escape the sandbox directory.

    The file names here come from project records and, in the fix loop, from a
    model's output. ``../../etc/passwd`` as a filename would otherwise be
    written wherever the tar extraction pointed it.
    """
    cleaned = name.replace("\\", "/").lstrip("/")
    parts = [
        part for part in cleaned.split("/") if part not in ("", ".", "..")
    ]

    if not parts:
        raise ExecutionError(f"Refusing to write a file named {name!r}.")

    return "/".join(parts)


def _docker_client():
    try:
        import docker
        from docker.errors import DockerException
    except ImportError as exc:
        raise SandboxUnavailable(
            "The docker package is not installed. Run: pip install -r requirements.txt"
        ) from exc

    try:
        client = docker.from_env()
        client.ping()
    except DockerException as exc:
        raise SandboxUnavailable(
            "Cannot reach the Docker daemon. Start Docker Desktop, or set "
            "EXECUTION_BACKEND=local for unsandboxed local execution."
        ) from exc

    return client


def _run_in_docker(
    spec: RuntimeSpec,
    code: str,
    *,
    files: dict[str, str] | None = None,
    command: list[str] | None = None,
) -> ExecutionResult:
    """Run one submission, or a whole project, in a throwaway container.

    ``files`` and ``command`` are the project path used by the fix loop. They
    are optional so the original single-file call site is unchanged - the
    isolation settings below are shared by both, which is the point of not
    writing a second runner.
    """
    from docker.errors import APIError, ImageNotFound
    from requests.exceptions import ConnectionError as RequestsConnectionError
    from requests.exceptions import ReadTimeout

    client = _docker_client()

    try:
        client.images.get(spec.image)
    except ImageNotFound:
        logger.info("Pulling runtime image %s (first run only)", spec.image)
        client.images.pull(spec.image)

    container = client.containers.create(
        image=spec.image,
        command=command or spec.command,
        working_dir=f"/{SANDBOX_DIR}",
        # --- isolation ---
        network_disabled=True,
        read_only=True,
        user="65534:65534",
        cap_drop=["ALL"],
        security_opt=["no-new-privileges"],
        # --- resource ceilings ---
        mem_limit=EXECUTION_MEMORY_LIMIT,
        memswap_limit=EXECUTION_MEMORY_LIMIT,  # equal to mem_limit disables swap
        nano_cpus=int(EXECUTION_CPU_LIMIT * 1_000_000_000),
        pids_limit=EXECUTION_PIDS_LIMIT,
        # Scratch space, since the root filesystem is read-only.
        tmpfs={"/tmp": "rw,size=32m,mode=1777"},
        environment={
            "HOME": "/tmp",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "NODE_OPTIONS": "--max-old-space-size=128",
        },
    )

    try:
        payload = files if files is not None else {spec.filename: code}
        container.put_archive("/", _build_archive(payload))

        started_at = time.perf_counter()
        container.start()

        timed_out = False
        exit_code: int | None = None

        try:
            status = container.wait(timeout=EXECUTION_TIMEOUT_SECONDS)
            exit_code = status.get("StatusCode")
        except (ReadTimeout, RequestsConnectionError):
            timed_out = True

            try:
                container.kill()
            except APIError:
                pass  # Already gone.

        duration_ms = int((time.perf_counter() - started_at) * 1000)

        stdout = _truncate(container.logs(stdout=True, stderr=False))
        stderr = _truncate(container.logs(stdout=False, stderr=True))

        if timed_out:
            stderr += (
                f"\nExecution timed out after {EXECUTION_TIMEOUT_SECONDS}s "
                "and was terminated."
            )

        return ExecutionResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
            timed_out=timed_out,
            backend="docker",
        )
    finally:
        try:
            container.remove(force=True)
        except APIError:
            logger.warning("Failed to remove container %s", container.id, exc_info=True)


def _run_locally(
    spec: RuntimeSpec,
    code: str,
    *,
    files: dict[str, str] | None = None,
    command: list[str] | None = None,
) -> ExecutionResult:
    """Development-only fallback. No isolation beyond a timeout."""
    with tempfile.TemporaryDirectory() as workdir:
        source_path = os.path.join(workdir, spec.filename)
        payload = files if files is not None else {spec.filename: code}

        for name, content in payload.items():
            target = os.path.join(workdir, _safe_member_name(name))
            os.makedirs(os.path.dirname(target), exist_ok=True)

            with open(target, "w", encoding="utf-8") as handle:
                handle.write(content)

        started_at = time.perf_counter()
        timed_out = False
        exit_code: int | None = None
        stdout = ""
        stderr = ""

        argv = command if command else [*spec.local_command, source_path]

        # The container image guarantees a `python` on PATH; this host does
        # not - on Windows the name is frequently a Store stub that fails.
        # Only the local backend needs this, and only for the interpreter
        # already running us.
        if argv and argv[0] == "python":
            argv = [sys.executable, *argv[1:]]

        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                cwd=workdir,
                timeout=EXECUTION_TIMEOUT_SECONDS,
            )
            stdout = _truncate(completed.stdout)
            stderr = _truncate(completed.stderr)
            exit_code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = _truncate(exc.stdout or b"")
            stderr = _truncate(exc.stderr or b"")
            stderr += f"\nExecution timed out after {EXECUTION_TIMEOUT_SECONDS}s."
        except FileNotFoundError as exc:
            raise SandboxUnavailable(
                f"Runtime '{argv[0]}' is not installed on this host."
            ) from exc

        return ExecutionResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            timed_out=timed_out,
            backend="local",
        )
