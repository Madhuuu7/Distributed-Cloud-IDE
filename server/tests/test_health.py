"""/health is the only thing a deployed instance tells you without an account.

It reports which database engine is in use because the alternative - reading the
host's logs - is the difference between knowing a deploy keeps its data and
assuming it does.
"""


def test_health_reports_the_database_engine(client):
    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["database"] in {"sqlite", "postgresql"}


def test_health_reports_the_applied_schema_revision(client):
    from app.db.migrate import head_revision

    body = client.get("/health").json()

    assert body["schema_revision"] == head_revision()


def test_health_never_leaks_the_connection_string(client):
    """A connection string carries the password, and this endpoint is public."""
    from app.core.config import DATABASE_URL

    body = client.get("/health").json()
    serialised = " ".join(str(value) for value in body.values())

    assert DATABASE_URL not in serialised
    for secret in ("://", "@", "password"):
        assert secret not in serialised


def test_health_still_names_the_execution_backend_and_provider(client):
    body = client.get("/health").json()

    assert body["execution_backend"] == "local"
    assert body["ai_provider"] == "mock"
