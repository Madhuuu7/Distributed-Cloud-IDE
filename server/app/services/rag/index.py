"""Build and refresh a project's embedding index."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

import numpy as np
from sqlalchemy.orm import Session

from app.models.file import FileNode
from app.models.rag import CodeChunk, ProjectIndex
from app.services.ai import get_embedding_provider
from app.services.ai.base import ProviderError
from app.services.rag.chunker import chunk_file

logger = logging.getLogger(__name__)

# Vectors are stored as float32. float64 doubles the storage for precision that
# cosine similarity over normalised vectors cannot make use of.
VECTOR_DTYPE = np.float32

# Embedding providers charge and rate-limit per request, so chunks go up in
# batches rather than one at a time.
EMBED_BATCH_SIZE = 64


def pack_vector(values: list[float]) -> bytes:
    return np.asarray(values, dtype=VECTOR_DTYPE).tobytes()


def unpack_vector(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=VECTOR_DTYPE)


def fingerprint_project(files: list[FileNode]) -> str:
    """A hash of a project's content, used to detect a stale index.

    Sorted by file id so the same set of files always produces the same digest
    regardless of the order the database returned them in.
    """
    digest = hashlib.sha256()

    for file_node in sorted(files, key=lambda f: f.id):
        digest.update(str(file_node.id).encode())
        digest.update(file_node.name.encode())
        digest.update(file_node.content.encode())

    return digest.hexdigest()


def get_or_create_index(db: Session, project_id: int) -> ProjectIndex:
    index = db.get(ProjectIndex, project_id)

    if index is None:
        index = ProjectIndex(project_id=project_id)
        db.add(index)
        db.commit()
        db.refresh(index)

    return index


def is_stale(db: Session, project_id: int) -> bool:
    index = db.get(ProjectIndex, project_id)

    if index is None or index.status != "ready":
        return True

    files = db.query(FileNode).filter(FileNode.project_id == project_id).all()

    return index.source_fingerprint != fingerprint_project(files)


def build_index(db: Session, project_id: int) -> ProjectIndex:
    """Chunk, embed, and store every file in a project.

    The rebuild is destructive and total rather than incremental. For a project
    of this size that is the right trade: incremental updates need per-chunk
    invalidation logic whose bugs show up as silently stale answers, which is
    the worst failure mode a retrieval system has.
    """
    index = get_or_create_index(db, project_id)
    index.status = "building"
    index.error = None
    db.commit()

    try:
        files = db.query(FileNode).filter(FileNode.project_id == project_id).all()

        chunks = []

        for file_node in files:
            for chunk in chunk_file(
                file_node.name, file_node.content, file_node.language
            ):
                chunks.append((file_node.id, chunk))

        provider = get_embedding_provider()

        if not provider.is_configured:
            raise ProviderError(
                f"Embedding provider '{provider.name}' is not configured."
            )

        db.query(CodeChunk).filter(CodeChunk.project_id == project_id).delete()

        for start in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[start : start + EMBED_BATCH_SIZE]
            vectors = provider.embed([chunk.text for _, chunk in batch])

            if len(vectors) != len(batch):
                raise ProviderError(
                    f"Embedding provider returned {len(vectors)} vectors "
                    f"for {len(batch)} chunks."
                )

            for (file_id, chunk), vector in zip(batch, vectors):
                db.add(
                    CodeChunk(
                        project_id=project_id,
                        file_id=file_id,
                        path=chunk.path,
                        language=chunk.language,
                        symbol=chunk.symbol,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        text=chunk.text,
                        embedding=pack_vector(vector),
                        embedding_model=provider.model,
                        dimensions=len(vector),
                    )
                )

        index.status = "ready"
        index.chunk_count = len(chunks)
        index.embedding_model = provider.model
        index.dimensions = provider.embedding_dimensions
        index.source_fingerprint = fingerprint_project(files)
        index.indexed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(index)

        logger.info(
            "Indexed project %s: %s chunks from %s files",
            project_id,
            len(chunks),
            len(files),
        )

        return index

    except Exception as exc:
        # The failure is recorded on the index row rather than only logged, so
        # GET /projects/{id}/index can tell the user what went wrong instead of
        # leaving the status stuck on "building" with no explanation.
        db.rollback()
        index = get_or_create_index(db, project_id)
        index.status = "failed"
        index.error = str(exc)
        db.commit()

        raise
