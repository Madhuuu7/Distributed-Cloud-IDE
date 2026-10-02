"""The migrations have to describe the same schema the models do.

Nothing enforces that by construction: a column added to a model with no
matching revision leaves the tests passing - they build the schema from the
migrations - while every deployment is one column short. That is the failure
this project already hit once, under create_all. These tests are the guard.
"""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from app.db.migrate import alembic_config, current_revision, head_revision
from app.db.session import Base, engine


def test_migrations_leave_nothing_for_autogenerate_to_find():
    """An empty diff means the models and the migrations agree."""
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        difference = compare_metadata(context, Base.metadata)

    assert difference == [], (
        "The models and the migrations have drifted apart. Generate the "
        "missing revision with:\n"
        "    cd server && alembic revision --autogenerate -m 'describe it'\n"
        f"Outstanding differences: {difference}"
    )


def test_the_database_is_stamped_at_head():
    assert current_revision() == head_revision()


def test_every_migration_can_be_undone():
    """A downgrade path is what makes a bad deploy recoverable."""
    config = alembic_config()

    command.downgrade(config, "base")
    assert current_revision() is None

    command.upgrade(config, "head")
    assert current_revision() == head_revision()


def test_the_workspace_column_create_all_could_not_add_is_present():
    """The column whose absence was the original bug.

    create_all adds missing tables but never missing columns, so a database
    created before workspaces existed kept a projects table with no
    workspace_id and failed only when someone created a project.
    """
    from sqlalchemy import inspect

    columns = {column["name"] for column in inspect(engine).get_columns("projects")}

    assert "workspace_id" in columns
