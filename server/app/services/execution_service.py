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

    if EXECUTION_BACKEND == "local":
        logger.warning("Executing user code with the unsandboxed local backend")
        return _run_locally(spec, code)

    return _run_in_docker(spec, code)


def _truncate(raw: bytes) -> str:
    if len(raw) > EXECUTION_MAX_OUTPUT_BYTES:
        head = raw[:EXECUTION_MAX_OUTPUT_BYTES].decode("utf-8", "replace")
        return head + TRUNCATION_NOTICE

    return raw.decode("utf-8", "replace")


def _build_code_archive(filename: str, code: str) -> bytes:
    """Tar the submission so it can be copied into the container before start."""
    data = code.encode("utf-8")
    buffer = io.BytesIO()

    with tarfile.open(fileobj=buffer, mode="w") as tar:
        directory = tarfile.TarInfo(SANDBOX_DIR)
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o555
        tar.addfile(directory)

        member = tarfile.TarInfo(f"{SANDBOX_DIR}/{filename}")
        member.size = len(data)
        member.mode = 0o444
        tar.addfile(member, io.BytesIO(data))

    return buffer.getvalue()


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


def _run_in_docker(spec: RuntimeSpec, code: str) -> ExecutionResult:
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
        command=spec.command,
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
        container.put_archive("/", _build_code_archive(spec.filename, code))

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


def _run_locally(spec: RuntimeSpec, code: str) -> ExecutionResult:
    """Development-only fallback. No isolation beyond a timeout."""
    with tempfile.TemporaryDirectory() as workdir:
        source_path = os.path.join(workdir, spec.filename)

        with open(source_path, "w", encoding="utf-8") as handle:
            handle.write(code)

        started_at = time.perf_counter()
        timed_out = False
        exit_code: int | None = None
        stdout = ""
        stderr = ""

        try:
            completed = subprocess.run(
                [*spec.local_command, source_path],
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
                f"Runtime '{spec.local_command[0]}' is not installed on this host."
            ) from exc

        return ExecutionResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            timed_out=timed_out,
            backend="local",
        )
