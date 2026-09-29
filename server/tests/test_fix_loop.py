"""The agentic fix loop, end to end.

The model is scripted here rather than mocked away. What is under test is
everything around it: that a baseline failure is detected, that the proposed
patch is actually executed in the sandbox, that a passing patch stops the loop,
that a patch which never passes is given up on, and that nothing reaches the
project's files until a human approves it.

Scripting the model is what makes those assertions possible at all - a real one
would sometimes fix the bug and sometimes not, and a test that passes
sometimes is not a test.
"""

import json

import pytest

from app.services.ai import registry
from app.services.ai.base import Completion, Usage
from app.services.ai.mock import MockProvider

BUGGY = "def add(a, b):\n    return a - b\n"
FIXED = "def add(a, b):\n    return a + b\n"

TEST_FILE = """import unittest

from calc import add


class AddTest(unittest.TestCase):
    def test_adds(self):
        self.assertEqual(add(2, 3), 5)
"""


class ScriptedProvider(MockProvider):
    """A provider that returns a prepared sequence of patches."""

    def __init__(self, patches):
        self._patches = list(patches)
        self.calls = 0

    def complete(self, messages, *, feature="chat", **kwargs):
        if feature != "fix":
            return super().complete(messages, feature=feature, **kwargs)

        self.calls += 1
        # Past the end of the script, keep returning the last patch - that is
        # how a model stuck in a loop behaves, which is the case the iteration
        # cap exists for.
        patch = self._patches[min(self.calls, len(self._patches)) - 1]

        return Completion(
            text=json.dumps(patch),
            model="scripted-1",
            usage=Usage(prompt_tokens=100, completion_tokens=50),
        )


def patch_of(content, summary="Fix the operator"):
    return {
        "summary": summary,
        "reasoning": "The test expects addition but the code subtracts.",
        "changes": [{"path": "calc.py", "content": content}],
    }


@pytest.fixture
def scripted(monkeypatch):
    def install(patches):
        provider = ScriptedProvider(patches)
        # AI_PROVIDER is "mock" under test, and get_provider() memoises
        # instances, so replacing the cached entry redirects every call.
        monkeypatch.setitem(registry._instances, "mock", provider)

        return provider

    return install


@pytest.fixture
def broken_project(client, auth_headers):
    project = client.post(
        "/projects", json={"name": "Calculator"}, headers=auth_headers
    ).json()

    for name, content in (("calc.py", BUGGY), ("test_calc.py", TEST_FILE)):
        response = client.post(
            f"/projects/{project['id']}/files",
            json={"name": name, "content": content},
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text

    return project


def start_run(client, headers, project_id, **kwargs):
    response = client.post(
        "/fix-runs",
        json={
            "project_id": project_id,
            "instruction": "Make the failing test pass.",
            **kwargs,
        },
        headers=headers,
    )
    assert response.status_code == 202, response.text

    return response.json()


def test_a_working_patch_stops_the_loop(
    client, auth_headers, broken_project, scripted
):
    provider = scripted([patch_of(FIXED)])

    run = start_run(client, auth_headers, broken_project["id"])
    detail = client.get(f"/fix-runs/{run['id']}", headers=auth_headers).json()

    assert detail["status"] == "awaiting_approval"
    assert provider.calls == 1

    # Iteration 0 is the baseline failure; iteration 1 is the fix.
    assert [i["iteration"] for i in detail["iterations"]] == [0, 1]
    assert detail["iterations"][0]["passed"] is False
    assert detail["iterations"][1]["passed"] is True

    # The diff is derived from the files, not taken from the model.
    assert "-    return a - b" in detail["diff"]
    assert "+    return a + b" in detail["diff"]


def test_the_patch_is_not_applied_without_approval(
    client, auth_headers, broken_project, scripted
):
    """The rule that makes the whole feature safe to leave switched on."""
    scripted([patch_of(FIXED)])

    start_run(client, auth_headers, broken_project["id"])

    files = client.get(
        f"/projects/{broken_project['id']}/files", headers=auth_headers
    ).json()
    calc = next(f for f in files if f["name"] == "calc.py")
    content = client.get(
        f"/projects/file/{calc['id']}", headers=auth_headers
    ).json()["content"]

    assert content == BUGGY


def test_apply_writes_the_patch(client, auth_headers, broken_project, scripted):
    scripted([patch_of(FIXED)])

    run = start_run(client, auth_headers, broken_project["id"])
    applied = client.post(
        f"/fix-runs/{run['id']}/apply", headers=auth_headers
    )

    assert applied.status_code == 200
    assert applied.json()["applied_paths"] == ["calc.py"]

    files = client.get(
        f"/projects/{broken_project['id']}/files", headers=auth_headers
    ).json()
    calc = next(f for f in files if f["name"] == "calc.py")
    content = client.get(
        f"/projects/file/{calc['id']}", headers=auth_headers
    ).json()["content"]

    assert content == FIXED
    assert client.get(
        f"/fix-runs/{run['id']}", headers=auth_headers
    ).json()["status"] == "succeeded"


def test_it_retries_after_a_failed_patch(
    client, auth_headers, broken_project, scripted
):
    """The loop's reason for existing: a wrong first attempt is recoverable."""
    wrong = "def add(a, b):\n    return a * b\n"
    provider = scripted([patch_of(wrong, "Try multiplication"), patch_of(FIXED)])

    run = start_run(client, auth_headers, broken_project["id"], max_iterations=3)
    detail = client.get(f"/fix-runs/{run['id']}", headers=auth_headers).json()

    assert provider.calls == 2
    assert detail["status"] == "awaiting_approval"
    assert [i["passed"] for i in detail["iterations"]] == [False, False, True]


def test_it_gives_up_at_the_iteration_cap(
    client, auth_headers, broken_project, scripted
):
    """A model that never gets it right must not burn tokens forever."""
    never = "def add(a, b):\n    return a * b\n"
    provider = scripted([patch_of(never)])

    run = start_run(client, auth_headers, broken_project["id"], max_iterations=2)
    detail = client.get(f"/fix-runs/{run['id']}", headers=auth_headers).json()

    assert provider.calls == 2
    assert detail["status"] == "failed"
    assert "2 attempts" in detail["error"]


def test_already_passing_tests_are_reported_honestly(
    client, auth_headers, scripted
):
    """A green suite is not a fix, and must not be recorded as one."""
    provider = scripted([patch_of(FIXED)])

    project = client.post(
        "/projects", json={"name": "Working"}, headers=auth_headers
    ).json()

    for name, content in (("calc.py", FIXED), ("test_calc.py", TEST_FILE)):
        client.post(
            f"/projects/{project['id']}/files",
            json={"name": name, "content": content},
            headers=auth_headers,
        )

    run = start_run(client, auth_headers, project["id"])
    detail = client.get(f"/fix-runs/{run['id']}", headers=auth_headers).json()

    assert detail["status"] == "succeeded"
    assert "already passed" in detail["summary"]
    # The model was never called, so the run cost nothing.
    assert provider.calls == 0


def test_a_no_op_patch_does_not_count_as_a_fix(
    client, auth_headers, broken_project, scripted
):
    provider = scripted([patch_of(BUGGY, "Change nothing")])

    run = start_run(client, auth_headers, broken_project["id"], max_iterations=1)
    detail = client.get(f"/fix-runs/{run['id']}", headers=auth_headers).json()

    assert provider.calls == 1
    assert detail["status"] == "failed"
    # The patch was recorded but never executed - there was nothing to test.
    assert detail["iterations"][1]["exit_code"] is None


def test_malformed_model_output_is_survivable(
    client, auth_headers, broken_project, monkeypatch
):
    class GarbageProvider(MockProvider):
        def complete(self, messages, *, feature="chat", **kwargs):
            if feature != "fix":
                return super().complete(messages, feature=feature, **kwargs)

            return Completion(
                text="Sure! Here's the fix: ```python\ndef add(): ...\n```",
                model="scripted-1",
                usage=Usage(prompt_tokens=10, completion_tokens=10),
            )

    monkeypatch.setitem(registry._instances, "mock", GarbageProvider())

    run = start_run(client, auth_headers, broken_project["id"], max_iterations=1)
    detail = client.get(f"/fix-runs/{run['id']}", headers=auth_headers).json()

    assert detail["status"] == "failed"
    assert "could not be parsed" in detail["iterations"][1]["reasoning"]


def test_concurrent_runs_on_one_project_are_rejected(
    client, auth_headers, broken_project, monkeypatch
):
    """Two agents editing the same files would each test stale state."""
    from app.models.fix import FixRun
    from app.db.session import SessionLocal

    # Leave a run in flight without executing it.
    db = SessionLocal()
    db.add(
        FixRun(
            project_id=broken_project["id"],
            user_id=1,
            instruction="stuck",
            status="running",
        )
    )
    db.commit()
    db.close()

    response = client.post(
        "/fix-runs",
        json={"project_id": broken_project["id"], "instruction": "another"},
        headers=auth_headers,
    )

    assert response.status_code == 409


def test_a_viewer_cannot_start_a_fix_run(client, auth_headers, scripted):
    """Otherwise a read-only member could spend the owner's token budget."""
    from tests.conftest import register

    scripted([patch_of(FIXED)])

    workspace = client.post(
        "/workspaces", json={"name": "Team"}, headers=auth_headers
    ).json()
    register(client, email="viewer@example.com")
    viewer = client.post(
        "/auth/login",
        json={"email": "viewer@example.com", "password": "supersecret123"},
    )
    viewer_headers = {
        "Authorization": f"Bearer {viewer.json()['access_token']}"
    }
    client.post(
        f"/workspaces/{workspace['id']}/members",
        json={"email": "viewer@example.com", "role": "viewer"},
        headers=auth_headers,
    )

    project = client.post(
        "/projects",
        json={"name": "Shared", "workspace_id": workspace["id"]},
        headers=auth_headers,
    ).json()

    response = client.post(
        "/fix-runs",
        json={"project_id": project["id"], "instruction": "fix it"},
        headers=viewer_headers,
    )

    assert response.status_code == 403


def test_apply_requires_a_patch_awaiting_approval(
    client, auth_headers, broken_project, scripted
):
    never = "def add(a, b):\n    return a * b\n"
    scripted([patch_of(never)])

    run = start_run(client, auth_headers, broken_project["id"], max_iterations=1)
    response = client.post(f"/fix-runs/{run['id']}/apply", headers=auth_headers)

    assert response.status_code == 409
