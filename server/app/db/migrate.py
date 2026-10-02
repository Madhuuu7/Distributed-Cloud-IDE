"""Where the schema version lives, and how the app checks it.

The application never creates or alters tables on its own. It used to, via
``Base.metadata.create_all``, which adds missing *tables* but never missing
*columns* - so a database created before a feature landed stayed silently one
column short, and the failure surfaced as a 500 from deep inside a request
rather than at startup. Alembic owns the schema now, and startup only checks
that the database agrees with the migrations.
"""

from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.db.session import engine

SERVER_DIR = Path(__file__).resolve().parent.parent.parent
ALEMBIC_INI = SERVER_DIR / "alembic.ini"
MIGRATIONS_DIR = SERVER_DIR / "migrations"


def alembic_config() -> Config:
    """An Alembic config that works from any working directory."""
    config = Config(str(ALEMBIC_INI))
    # alembic.ini names the script location relatively, which only resolves
    # when alembic is invoked from server/. Tests and the app are not.
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


def head_revision() -> str:
    """The newest revision the migration scripts define."""
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current_revision() -> str | None:
    """The revision the database is stamped with, or None if it has never been migrated."""
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def assert_schema_is_current() -> None:
    """Refuse to start against a database the migrations have moved past.

    A stale schema is the one failure mode that looks like a working app until
    the request that needs the missing column arrives, so it is worth a startup
    failure that names the command that fixes it.
    """
    head = head_revision()
    current = current_revision()

    if current == head:
        return

    if current is None:
        raise RuntimeError(
            "This database has no schema yet. Create it with:\n"
            "    cd server && alembic upgrade head"
        )

    raise RuntimeError(
        f"Database schema is at revision {current!r} but the migrations are at "
        f"{head!r}. Bring it up to date with:\n"
        "    cd server && alembic upgrade head"
    )
