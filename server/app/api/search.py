"""Index management and semantic code search."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.access import enforce_ai_rate_limit, not_found, resolve_project_role
from app.core.deps import get_current_user, get_db
from app.db.session import SessionLocal
from app.models.project import Project
from app.models.rag import CodeChunk, ProjectIndex
from app.models.user import User
from app.schemas.search import (
    IndexStatus,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from app.services.ai.base import ProviderError
from app.services.rag.index import build_index, get_or_create_index, is_stale
from app.services.rag.search import search as run_search

logger = logging.getLogger(__name__)

router = APIRouter()


def _readable_project(db: Session, user: User, project_id: int) -> Project:
    project = db.get(Project, project_id)

    if project is None or resolve_project_role(db, project, user) is None:
        raise not_found

    return project


def _index_in_background(project_id: int) -> None:
    """Run the index build on its own session.

    The request's session is closed by the time a background task runs, so
    reusing it would fail at the first query. Errors are swallowed here
    deliberately - they are already recorded on the index row, which is where
    the client looks.
    """
    db = SessionLocal()

    try:
        build_index(db, project_id)
    except Exception:
        logger.exception("Background index build failed for project %s", project_id)
    finally:
        db.close()


def _status_payload(db: Session, project_id: int) -> IndexStatus:
    index = get_or_create_index(db, project_id)

    return IndexStatus(
        project_id=project_id,
        status=index.status,
        chunk_count=index.chunk_count,
        embedding_model=index.embedding_model,
        dimensions=index.dimensions,
        indexed_at=index.indexed_at,
        stale=is_stale(db, project_id),
        error=index.error,
    )


@router.post(
    "/projects/{project_id}/index",
    response_model=IndexStatus,
    status_code=status.HTTP_202_ACCEPTED,
)
def reindex_project(
    project_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(enforce_ai_rate_limit),
) -> IndexStatus:
    """Queue a rebuild of a project's embedding index.

    Returns ``202`` rather than blocking: embedding a project of any size means
    several provider round trips, and holding an HTTP request open for them
    produces timeouts on exactly the projects worth indexing.
    """
    _readable_project(db, current_user, project_id)

    index = get_or_create_index(db, project_id)

    if index.status == "building":
        raise HTTPException(
            status_code=409,
            detail="An index build is already running for this project.",
        )

    index.status = "building"
    index.error = None
    db.commit()

    background_tasks.add_task(_index_in_background, project_id)

    return _status_payload(db, project_id)


@router.get("/projects/{project_id}/index", response_model=IndexStatus)
def index_status(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IndexStatus:
    _readable_project(db, current_user, project_id)

    return _status_payload(db, project_id)


@router.delete("/projects/{project_id}/index")
def drop_index(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    _readable_project(db, current_user, project_id)

    db.query(CodeChunk).filter(CodeChunk.project_id == project_id).delete()

    index = db.get(ProjectIndex, project_id)

    if index is not None:
        index.status = "empty"
        index.chunk_count = 0
        index.source_fingerprint = None
        index.indexed_at = None

    db.commit()

    return {"message": "Index dropped"}


@router.post("/search", response_model=SearchResponse)
def search_code(
    payload: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(enforce_ai_rate_limit),
) -> SearchResponse:
    _readable_project(db, current_user, payload.project_id)

    total = (
        db.query(CodeChunk)
        .filter(CodeChunk.project_id == payload.project_id)
        .count()
    )

    if total == 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "This project has not been indexed yet. "
                f"POST /projects/{payload.project_id}/index first."
            ),
        )

    try:
        hits = run_search(
            db,
            project_id=payload.project_id,
            query=payload.query,
            k=payload.k,
        )
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return SearchResponse(
        query=payload.query,
        searched_chunks=total,
        results=[
            SearchResult(
                path=hit.chunk.path,
                symbol=hit.chunk.symbol,
                language=hit.chunk.language,
                start_line=hit.chunk.start_line,
                end_line=hit.chunk.end_line,
                text=hit.chunk.text,
                score=round(hit.score, 4),
                keyword_score=round(hit.keyword_score, 4),
                vector_score=round(hit.vector_score, 4),
            )
            for hit in hits
        ],
    )
