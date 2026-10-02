import os
import tempfile
from pathlib import Path

import pytest

# Point the app at a throwaway database before anything imports app.core.config.
_TEMP_DB = Path(tempfile.gettempdir()) / "dcide_test.db"
os.environ["DB_PATH"] = str(_TEMP_DB)
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["EXECUTION_BACKEND"] = "local"

from alembic import command  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.migrate import alembic_config  # noqa: E402
from app.db.session import Base, engine  # noqa: E402

# app.main refuses to import against an unmigrated database, exactly as it would
# refuse to boot against one. Build the schema first, like a deploy does.
command.upgrade(alembic_config(), "head")

from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_database():
    # Built by the migrations rather than by create_all, so every test runs
    # against the schema a deploy would actually get. The two cannot drift
    # without the suite noticing - which is the whole point, given that a
    # stale schema is what create_all let through in the first place.
    _drop_everything()
    command.upgrade(alembic_config(), "head")
    yield
    _drop_everything()


def _drop_everything():
    Base.metadata.drop_all(bind=engine)

    # drop_all knows nothing about alembic_version, and leaving it behind would
    # tell the next upgrade the schema is already at head.
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def register(client, email="dev@example.com", password="supersecret123"):
    """Create a user and return an Authorization header for them."""
    response = client.post(
        "/auth/signup",
        json={"email": email, "password": password, "full_name": "Dev User"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers(client):
    return register(client)
