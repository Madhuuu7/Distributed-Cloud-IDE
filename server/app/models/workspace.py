from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

# Ordered by privilege. Comparing positions in this tuple is how every
# permission check is expressed, so adding a role between two existing ones is
# a single-line change rather than an audit of every endpoint.
ROLE_ORDER: tuple[str, ...] = ("viewer", "editor", "owner")


def role_at_least(role: str, required: str) -> bool:
    try:
        return ROLE_ORDER.index(role) >= ROLE_ORDER.index(required)
    except ValueError:
        # An unknown role denies rather than crashes: a bad row in the members
        # table should lock someone out, never grant them access.
        return False


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    # One row per person per workspace. Without this constraint a repeated
    # invite would silently create a second membership, and which role applied
    # would depend on row order.
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), default="editor", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkspaceMessage(Base):
    """A message in a workspace's chat.

    ``file_id`` and ``line`` are optional so the same table serves both room
    chat and a comment anchored to a line of code - they are the same object
    to a reader, and splitting them would mean two feeds to merge.
    """

    __tablename__ = "workspace_messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    file_id: Mapped[int | None] = mapped_column(
        ForeignKey("files.id"), nullable=True
    )
    line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
