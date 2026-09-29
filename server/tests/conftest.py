import os
import tempfile
from pathlib import Path

import pytest

# Point the app at a throwaway database before anything imports app.core.config.
_TEMP_DB = Path(tempfile.gettempdir()) / "dcide_test.db"
os.environ["DB_PATH"] = str(_TEMP_DB)
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["EXECUTION_BACKEND"] = "local"

from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


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
