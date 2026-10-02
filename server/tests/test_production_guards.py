"""The two settings that are safe to get wrong locally and dangerous in production.

Both guards are startup failures rather than warnings, because a warning in a
deploy log is a thing nobody reads until after the incident. They are tested by
re-importing the config module under patched environment variables - the checks
live at import time, which is exactly when they need to fire.
"""

import importlib

import pytest


def reload_config(monkeypatch, **environment):
    """Re-import app.core.config with a patched environment."""
    # Reloading the module re-runs load_dotenv, which would read the .env file
    # the README tells you to create and put a real SECRET_KEY back into the
    # environment this test just cleared. The scenario under test could then
    # never occur - so these tests passed on a clean checkout and failed for
    # anyone who had actually followed the setup instructions.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)

    for key, value in environment.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)

    import app.core.config as config

    return importlib.reload(config)


@pytest.fixture(autouse=True)
def restore_config():
    """Put the real module back, so later tests import the config they expect."""
    yield

    import app.core.config as config

    importlib.reload(config)


def test_production_rejects_the_default_secret_key(monkeypatch):
    """A signing key published on GitHub is the same as no authentication."""
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        reload_config(
            monkeypatch,
            APP_ENV="production",
            SECRET_KEY=None,
            EXECUTION_BACKEND="disabled",
        )


def test_production_accepts_a_real_secret_key(monkeypatch):
    config = reload_config(
        monkeypatch,
        APP_ENV="production",
        SECRET_KEY="a-real-generated-key",
        EXECUTION_BACKEND="disabled",
    )

    assert config.IS_PRODUCTION is True
    assert config.EXECUTION_BACKEND == "disabled"


def test_production_refuses_the_unsandboxed_backend(monkeypatch):
    """EXECUTION_BACKEND=local on a public URL is remote code execution."""
    with pytest.raises(RuntimeError, match="no isolation"):
        reload_config(
            monkeypatch,
            APP_ENV="production",
            SECRET_KEY="a-real-generated-key",
            EXECUTION_BACKEND="local",
        )


def test_development_still_allows_both_defaults(monkeypatch):
    """Local development must stay frictionless - that is the whole point."""
    config = reload_config(
        monkeypatch,
        APP_ENV="development",
        SECRET_KEY=None,
        EXECUTION_BACKEND="local",
    )

    assert config.SECRET_KEY == config.DEV_SECRET_KEY
    assert config.EXECUTION_BACKEND == "local"


def test_an_unknown_backend_is_rejected(monkeypatch):
    """A typo in a deploy variable should fail loudly, not pick a default."""
    with pytest.raises(RuntimeError, match="must be"):
        reload_config(
            monkeypatch,
            APP_ENV="development",
            EXECUTION_BACKEND="dcoker",
        )


def test_disabled_backend_returns_503(client, auth_headers, monkeypatch):
    """The deployed demo must say why execution is off, not just fail."""
    from app.services import execution_service

    monkeypatch.setattr(execution_service, "EXECUTION_BACKEND", "disabled")

    response = client.post(
        "/execute",
        json={"language": "python", "code": "print('hi')"},
        headers=auth_headers,
    )

    assert response.status_code == 503
    assert "switched off" in response.json()["detail"]
