from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CodeChunk(Base):
    """One retrievable unit of code, with its embedding.

    The vector is stored as raw ``float32`` bytes rather than JSON. A 768-dim
    vector is 3 KB packed and roughly 15 KB as a JSON array of decimal strings,
    and the packed form loads straight into NumPy with no parse step. Scoring a
    few thousand chunks per query makes that difference visible.
    """

    __tablename__ = "code_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), nullable=False, index=True
    )
    file_id: Mapped[int | None] = mapped_column(
        ForeignKey("files.id"), nullable=True, index=True
    )

    path: Mapped[str] = mapped_column(String(500), nullable=False)
    language: Mapped[str] = mapped_column(String(50), default="text", nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # Vectors from different models are not comparable. Recording the model and
    # its dimensionality is what lets the index detect that it was built with a
    # provider that is no longer configured, instead of returning nonsense.
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProjectIndex(Base):
    """Index state for one project.

    ``source_fingerprint`` is a hash of every file's content. Comparing it
    against the project's current files is how ``GET /projects/{id}/index``
    answers "is this stale?" without re-embedding anything.
    """

    __tablename__ = "project_indexes"

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(20), default="empty", nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
