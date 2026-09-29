"""Verifies that authentication is actually enforced, not just present."""

import pytest

from tests.conftest import register

PROTECTED_ENDPOINTS = [
    ("get", "/auth/me"),
    ("get", "/projects"),
    ("post", "/projects"),
    ("get", "/projects/1"),
    ("delete", "/projects/1"),
    ("get", "/projects/1/files"),
    ("post", "/projects/1/files"),
    ("get", "/projects/file/1"),
    ("put", "/projects/file/1"),
    ("delete", "/projects/file/1"),
    ("post", "/execute"),
    ("get", "/execute/languages"),
]


@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
def test_endpoint_rejects_anonymous_requests(client, method, path):
    response = client.request(method, path, json={})
    assert response.status_code == 401, f"{method.upper()} {path} was reachable anonymously"


@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
def test_endpoint_rejects_garbage_token(client, method, path):
    response = client.request(
        method,
        path,
        json={},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401


def test_signup_then_me_returns_the_caller(client):
    headers = register(client, email="Madhura@Example.com")
    response = client.get("/auth/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "madhura@example.com"  # normalized to lowercase
    assert body["full_name"] == "Dev User"
    assert "password_hash" not in body


def test_duplicate_signup_is_rejected(client):
    register(client, email="dup@example.com")
    response = client.post(
        "/auth/signup",
        json={"email": "dup@example.com", "password": "supersecret123"},
    )
    assert response.status_code == 400


def test_short_password_is_rejected(client):
    response = client.post(
        "/auth/signup",
        json={"email": "weak@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_login_is_case_insensitive_on_email(client):
    register(client, email="case@example.com", password="supersecret123")
    response = client.post(
        "/auth/login",
        json={"email": "CASE@example.com", "password": "supersecret123"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_login_with_wrong_password_fails(client):
    register(client, email="real@example.com", password="supersecret123")
    response = client.post(
        "/auth/login",
        json={"email": "real@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401


def test_a_password_longer_than_bcrypt_s_limit_still_works(client):
    """bcrypt reads at most 72 bytes; the password is pre-hashed so it fits.

    Without that step this is either a silent truncation (every 72+ byte
    password sharing a prefix becomes the same password) or, on modern bcrypt,
    a 500 on signup.
    """
    # 87 bytes: past bcrypt's 72-byte limit, inside the schema's 128-char cap.
    # That window is exactly where the truncation bug lives.
    long_password = "correct-horse-battery-staple-" * 3

    signup = client.post(
        "/auth/signup",
        json={"email": "long@example.com", "password": long_password},
    )
    assert signup.status_code == 201, signup.text

    login = client.post(
        "/auth/login",
        json={"email": "long@example.com", "password": long_password},
    )
    assert login.status_code == 200

    # The truncation bug would make this succeed, since it shares the first
    # 72 bytes with the real password.
    wrong = client.post(
        "/auth/login",
        json={"email": "long@example.com", "password": long_password + "-wrong"},
    )
    assert wrong.status_code == 401


def test_a_corrupt_stored_hash_is_a_failed_login_not_a_crash(client, auth_headers):
    from app.core.security import verify_password

    assert verify_password("anything", "not-a-real-bcrypt-hash") is False
