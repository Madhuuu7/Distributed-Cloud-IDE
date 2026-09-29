"""The AI surface: retrieval, chat grounding, caching, and cost accounting.

These run against the mock provider, which is the point of having one - the
retrieval pipeline, the cache, the usage ledger, and the rate limiter are all
exercised for real, with no API key and no spend. Only the quality of the
generated prose is mocked out, and that is the one thing a test could not
assert on anyway.
"""

import pytest

from app.core.access import ai_rate_limiter
from app.services.ai.cache import prompt_cache

SAMPLE = """import os

SECRET_KEY = os.getenv("SECRET_KEY")


def verify_access_token(token):
    \"\"\"Decode a bearer token and return its subject.\"\"\"
    return decode(token, SECRET_KEY)


def list_invoices(customer_id):
    return db.query(Invoice).filter(Invoice.customer == customer_id).all()
"""


@pytest.fixture(autouse=True)
def reset_ai_state():
    """Isolate the in-process cache and rate limiter between tests.

    Both are module-level singletons, so without this a test that fills the
    rate limit makes every later test fail, and a cache hit from one test
    leaks into another's assertions.
    """
    prompt_cache.clear()
    ai_rate_limiter._calls.clear()

    yield

    prompt_cache.clear()
    ai_rate_limiter._calls.clear()


@pytest.fixture
def indexed_project(client, auth_headers):
    project = client.post(
        "/projects", json={"name": "Billing"}, headers=auth_headers
    ).json()

    client.post(
        f"/projects/{project['id']}/files",
        json={"name": "auth.py", "content": SAMPLE},
        headers=auth_headers,
    )

    response = client.post(
        f"/projects/{project['id']}/index", headers=auth_headers
    )
    assert response.status_code == 202, response.text

    return project


def test_providers_reports_mock_as_active(client, auth_headers):
    providers = client.get("/ai/providers", headers=auth_headers).json()
    active = [p for p in providers if p["active"]]

    assert len(active) == 1
    assert active[0]["name"] == "mock"
    assert active[0]["configured"] is True


def test_index_builds_and_reports_ready(client, auth_headers, indexed_project):
    status = client.get(
        f"/projects/{indexed_project['id']}/index", headers=auth_headers
    ).json()

    assert status["status"] == "ready"
    assert status["chunk_count"] > 0
    assert status["stale"] is False


def test_index_goes_stale_when_a_file_changes(
    client, auth_headers, indexed_project
):
    files = client.get(
        f"/projects/{indexed_project['id']}/files", headers=auth_headers
    ).json()

    client.put(
        f"/projects/file/{files[0]['id']}",
        json={"content": SAMPLE + "\n\ndef refund(invoice_id):\n    pass\n"},
        headers=auth_headers,
    )

    status = client.get(
        f"/projects/{indexed_project['id']}/index", headers=auth_headers
    ).json()

    # Reported, not silently repaired: reindexing costs money, so the decision
    # belongs to the caller.
    assert status["stale"] is True


def test_search_finds_the_right_function(client, auth_headers, indexed_project):
    response = client.post(
        "/search",
        json={
            "query": "verify access token",
            "project_id": indexed_project["id"],
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    results = response.json()["results"]

    assert results, "expected at least one hit"
    assert results[0]["symbol"] == "verify_access_token"
    # Both rankers are reported so a ranking can be explained.
    assert results[0]["keyword_score"] > 0
    assert 0.0 <= results[0]["score"] <= 1.0


def test_search_before_indexing_is_409(client, auth_headers):
    project = client.post(
        "/projects", json={"name": "Empty"}, headers=auth_headers
    ).json()

    response = client.post(
        "/search",
        json={"query": "anything", "project_id": project["id"]},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert "index" in response.json()["detail"].lower()


def test_chat_returns_citations_from_the_project(
    client, auth_headers, indexed_project
):
    response = client.post(
        "/ai/chat",
        json={
            "message": "How does token verification work?",
            "project_id": indexed_project["id"],
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()

    assert body["citations"], "a grounded answer must say what it was grounded in"
    assert body["citations"][0]["path"] == "auth.py"
    assert body["cached"] is False


def test_repeated_chat_hits_the_cache(client, auth_headers):
    """The same question in a fresh conversation is served from cache."""
    body = {"message": "What is a closure?", "use_rag": False}

    first = client.post("/ai/chat", json=body, headers=auth_headers).json()
    second = client.post("/ai/chat", json=body, headers=auth_headers).json()

    assert first["cached"] is False
    assert second["cached"] is True
    assert second["cost_usd"] == 0.0


def test_a_follow_up_is_not_a_cache_hit(client, auth_headers):
    """Repeating a message inside a conversation must re-ask the model.

    The prompt carries the prior turns, so the same words mean something
    different the second time. A cache that ignored history would answer a
    follow-up with the reply to the original question.
    """
    body = {"message": "What is a closure?", "use_rag": False}

    first = client.post("/ai/chat", json=body, headers=auth_headers).json()
    second = client.post(
        "/ai/chat",
        json={**body, "conversation_id": first["conversation_id"]},
        headers=auth_headers,
    ).json()

    assert second["cached"] is False


def test_conversation_history_is_persisted(client, auth_headers):
    first = client.post(
        "/ai/chat",
        json={"message": "First question", "use_rag": False},
        headers=auth_headers,
    ).json()

    client.post(
        "/ai/chat",
        json={
            "message": "Second question",
            "conversation_id": first["conversation_id"],
            "use_rag": False,
        },
        headers=auth_headers,
    )

    detail = client.get(
        f"/ai/conversations/{first['conversation_id']}", headers=auth_headers
    ).json()

    roles = [m["role"] for m in detail["messages"]]

    assert roles == ["user", "assistant", "user", "assistant"]


def test_conversations_are_private(client, auth_headers):
    from tests.conftest import register

    first = client.post(
        "/ai/chat",
        json={"message": "Private thoughts", "use_rag": False},
        headers=auth_headers,
    ).json()

    outsider = register(client, email="outsider@example.com")

    assert client.get(
        f"/ai/conversations/{first['conversation_id']}", headers=outsider
    ).status_code == 404


def test_explain_clamps_an_out_of_range_selection(client, auth_headers):
    project = client.post(
        "/projects", json={"name": "Billing"}, headers=auth_headers
    ).json()
    file_out = client.post(
        f"/projects/{project['id']}/files",
        json={"name": "auth.py", "content": SAMPLE},
        headers=auth_headers,
    ).json()

    response = client.post(
        "/ai/explain",
        json={"file_id": file_out["id"], "start_line": 1, "end_line": 9999},
        headers=auth_headers,
    )

    assert response.status_code == 200
    # Clamped to the file rather than rejected: a stale line count in the
    # editor should not produce an error.
    assert response.json()["end_line"] == len(SAMPLE.splitlines())


def test_review_drops_findings_for_unknown_files(client, auth_headers):
    """The mock provider cites `example.py`, which is not in this project.

    That is exactly the hallucination the filter exists to catch, so the mock
    doubles as a fixture for it.
    """
    project = client.post(
        "/projects", json={"name": "Billing"}, headers=auth_headers
    ).json()
    client.post(
        f"/projects/{project['id']}/files",
        json={"name": "auth.py", "content": SAMPLE},
        headers=auth_headers,
    )

    response = client.post(
        "/ai/review", json={"project_id": project["id"]}, headers=auth_headers
    )

    assert response.status_code == 200
    body = response.json()

    assert body["files_reviewed"] == 1
    assert body["findings"] == []


def test_usage_ledger_records_every_call(client, auth_headers):
    body = {"message": "Same question", "use_rag": False}

    client.post("/ai/chat", json=body, headers=auth_headers)
    client.post("/ai/chat", json=body, headers=auth_headers)

    usage = client.get("/ai/usage", headers=auth_headers).json()

    assert usage["total_calls"] == 2
    # One of the two was served from cache, so the hit rate is exactly half.
    assert usage["cache_hit_rate"] == 0.5
    assert [f["feature"] for f in usage["by_feature"]] == ["chat"]


def test_usage_is_per_user(client, auth_headers):
    from tests.conftest import register

    client.post(
        "/ai/chat",
        json={"message": "Mine", "use_rag": False},
        headers=auth_headers,
    )

    outsider = register(client, email="outsider@example.com")
    usage = client.get("/ai/usage", headers=outsider).json()

    assert usage["total_calls"] == 0


def test_rate_limit_returns_429_with_retry_after(client, auth_headers):
    from app.core.config import AI_RATE_LIMIT_PER_MINUTE

    last = None

    # One past the limit. Cached replies still count: the limiter guards the
    # endpoint, not the provider bill.
    for index in range(AI_RATE_LIMIT_PER_MINUTE + 1):
        last = client.post(
            "/ai/chat",
            json={"message": f"Question {index}", "use_rag": False},
            headers=auth_headers,
        )

    assert last.status_code == 429
    assert "Retry-After" in last.headers


def test_ai_endpoints_require_authentication(client):
    assert client.post("/ai/chat", json={"message": "hi"}).status_code == 401
    assert client.get("/ai/usage").status_code == 401
    assert client.post(
        "/search", json={"query": "x", "project_id": 1}
    ).status_code == 401
