"""Execution engine tests.

The sandbox-shape tests (archive layout, container arguments) run everywhere.
The end-to-end run tests use the local backend so they pass without a Docker
daemon; set EXECUTION_BACKEND=docker and run again to exercise the real sandbox.
"""

import io
import tarfile

import pytest

from app.services import execution_service
from app.services.execution_service import UnsupportedLanguage, run_code


def test_supported_languages_are_exposed(client, auth_headers):
    response = client.get("/execute/languages", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["languages"] == ["javascript", "python"]


def test_python_stdout_is_captured(client, auth_headers):
    response = client.post(
        "/execute",
        json={"language": "python", "code": "print('hello from the sandbox')"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert "hello from the sandbox" in body["stdout"]
    assert body["exit_code"] == 0
    assert body["timed_out"] is False
    assert body["duration_ms"] >= 0


def test_python_stderr_and_exit_code_are_separated(client, auth_headers):
    response = client.post(
        "/execute",
        json={"language": "python", "code": "raise ValueError('boom')"},
        headers=auth_headers,
    )

    body = response.json()
    assert body["stdout"] == ""
    assert "ValueError: boom" in body["stderr"]
    assert body["exit_code"] != 0


def test_timeout_is_reported_rather_than_hanging(client, auth_headers, monkeypatch):
    monkeypatch.setattr(execution_service, "EXECUTION_TIMEOUT_SECONDS", 1)

    response = client.post(
        "/execute",
        json={"language": "python", "code": "while True: pass"},
        headers=auth_headers,
    )

    body = response.json()
    assert body["timed_out"] is True
    assert "timed out" in body["stderr"].lower()


def test_unsupported_language_is_a_400(client, auth_headers):
    response = client.post(
        "/execute",
        json={"language": "cobol", "code": "DISPLAY 'hi'."},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "cobol" in response.json()["detail"].lower()


def test_run_code_rejects_unknown_language_directly():
    with pytest.raises(UnsupportedLanguage):
        run_code("brainfuck", "+++")


def test_oversized_output_is_truncated(monkeypatch):
    monkeypatch.setattr(execution_service, "EXECUTION_MAX_OUTPUT_BYTES", 32)
    result = execution_service._truncate(b"x" * 500)

    assert result.endswith(execution_service.TRUNCATION_NOTICE)
    assert len(result) < 500


def test_code_archive_puts_a_read_only_file_in_the_sandbox_dir():
    archive = execution_service._build_code_archive("main.py", "print(1)")

    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        names = tar.getnames()
        assert "sandbox" in names
        assert "sandbox/main.py" in names

        member = tar.getmember("sandbox/main.py")
        assert member.mode == 0o444
        assert tar.extractfile(member).read() == b"print(1)"


def test_docker_backend_applies_every_isolation_flag(monkeypatch):
    """Guards the sandbox settings against accidental loosening."""
    captured = {}

    class FakeContainer:
        id = "fake"

        def put_archive(self, path, data):
            captured["archive_path"] = path

        def start(self):
            pass

        def wait(self, timeout=None):
            captured["wait_timeout"] = timeout
            return {"StatusCode": 0}

        def logs(self, stdout=False, stderr=False):
            return b"ok" if stdout else b""

        def remove(self, force=False):
            captured["removed"] = force

    class FakeContainers:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeContainer()

    class FakeImages:
        def get(self, image):
            return image

    class FakeClient:
        containers = FakeContainers()
        images = FakeImages()

    monkeypatch.setattr(execution_service, "_docker_client", lambda: FakeClient())
    monkeypatch.setattr(execution_service, "EXECUTION_BACKEND", "docker")

    result = execution_service._run_in_docker(
        execution_service.RUNTIMES["python"], "print(1)"
    )

    assert result.backend == "docker"
    assert result.stdout == "ok"
    assert result.exit_code == 0

    assert captured["network_disabled"] is True
    assert captured["read_only"] is True
    assert captured["user"] == "65534:65534"
    assert captured["cap_drop"] == ["ALL"]
    assert captured["security_opt"] == ["no-new-privileges"]
    assert captured["mem_limit"] == captured["memswap_limit"]  # no swap escape
    assert captured["nano_cpus"] > 0
    assert captured["pids_limit"] > 0
    assert captured["working_dir"] == "/sandbox"
    assert captured["archive_path"] == "/"
    assert captured["removed"] is True


def test_docker_backend_kills_the_container_on_timeout(monkeypatch):
    from requests.exceptions import ReadTimeout

    events = []

    class FakeContainer:
        id = "fake"

        def put_archive(self, path, data):
            pass

        def start(self):
            pass

        def wait(self, timeout=None):
            raise ReadTimeout("too slow")

        def logs(self, stdout=False, stderr=False):
            return b""

        def kill(self):
            events.append("killed")

        def remove(self, force=False):
            events.append("removed")

    class FakeClient:
        class containers:
            @staticmethod
            def create(**kwargs):
                return FakeContainer()

        class images:
            @staticmethod
            def get(image):
                return image

    monkeypatch.setattr(execution_service, "_docker_client", lambda: FakeClient())

    result = execution_service._run_in_docker(
        execution_service.RUNTIMES["python"], "while True: pass"
    )

    assert result.timed_out is True
    assert result.exit_code is None
    assert events == ["killed", "removed"]
