from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

# queued      - accepted, not started
# running     - a worker is iterating
# awaiting_approval - a patch passed its tests and is waiting on a human
# succeeded   - the patch was applied
# failed      - iterations ran out, or the model gave up
# cancelled   - a human stopped it
FIX_STATUSES = (
    "queued",
    "running",
    "awaiting_approval",
    "succeeded",
    "failed",
    "cancelled",
)


class FixRun(Base):
    """One agentic attempt to make a project's tests pass.

    A run never writes to project files. It ends holding a proposed patch, and
    a human calls ``/apply``. Letting a model edit a workspace unattended is
    the difference between a tool people trust and one they turn off.
    """

    __tablename__ = "fix_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    # The command whose exit code decides success. Runs inside the same
    # network-isolated, read-only, memory-capped container as /execute.
    test_command: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    max_iterations: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The accepted patch, as JSON: {"summary": ..., "changes": [{path, content}]}
    # Whole-file contents, not a unified diff - models produce malformed diffs
    # far more often than they produce a malformed file, and the diff shown in
    # the UI is computed here from the before and after.
    proposed_patch: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class FixIteration(Base):
    """One patch-and-test cycle within a run.

    Every attempt is kept, including the ones that failed. The sequence of
    wrong answers and the failures that corrected them is the whole story of
    what the agent did.
    """

    __tablename__ = "fix_iterations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    fix_run_id: Mapped[int] = mapped_column(
        ForeignKey("fix_runs.id"), nullable=False, index=True
    )
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)

    patch: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
