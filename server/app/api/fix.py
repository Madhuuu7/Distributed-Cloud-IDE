"""Agentic fix runs: propose, verify in the sandbox, then wait for a human."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.access import enforce_ai_rate_limit, not_found, resolve_project_role
from app.core.deps import get_current_user, get_db
from app.db.session import SessionLocal
from app.models.fix import FixIteration, FixRun
from app.models.project import Project
from app.models.user import User
from app.models.workspace import role_at_least
from app.schemas.fix import (
    FixApplyResponse,
    FixIterationOut,
    FixRunCreate,
    FixRunDetail,
    FixRunOut,
)
from app.services.fix_service import (
    apply_patch,
    compute_diff,
    execute_fix_run,
    project_files,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _writable_project(db: Session, user: User, project_id: int) -> Project:
    """A fix run needs write access even before anything is written.

    Requiring only read access here would let a viewer queue runs that consume
    the project owner's token budget.
    """
    project = db.get(Project, project_id)

    if project is None:
        raise not_found

    role = resolve_project_role(db, project, user)

    if role is None:
        raise not_found

    if not role_at_least(role, "editor"):
        raise HTTPException(
            status_code=403,
            detail="Starting a fix run requires the 'editor' role or higher.",
        )

    return project


def _accessible_run(db: Session, user: User, run_id: int) -> FixRun:
    run = db.get(FixRun, run_id)

    if run is None:
        raise not_found

    project = db.get(Project, run.project_id)

    if project is None or resolve_project_role(db, project, user) is None:
        raise not_found

    return run


def _run_in_background(run_id: int) -> None:
    """Drive a run on its own session.

    The request's session is closed by the time this executes. Failures are
    written to the run row rather than raised, because there is no request left
    to return them to.
    """
    db = SessionLocal()

    try:
        execute_fix_run(db, run_id)
    except Exception as exc:
        logger.exception("Fix run %s crashed", run_id)

        run = db.get(FixRun, run_id)

        if run is not None:
            run.status = "failed"
            run.error = f"The run crashed: {exc}"
            db.commit()
    finally:
        db.close()


@router.post("", response_model=FixRunOut, status_code=status.HTTP_202_ACCEPTED)
def create_fix_run(
    payload: FixRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(enforce_ai_rate_limit),
) -> FixRun:
    _writable_project(db, current_user, payload.project_id)

    active = (
        db.query(FixRun)
        .filter(
            FixRun.project_id == payload.project_id,
            FixRun.status.in_(("queued", "running")),
        )
        .first()
    )

    # Two agents editing the same project concurrently would each test a patch
    # against files the other is about to change, and both results would be
    # meaningless.
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Fix run {active.id} is already running for this project.",
        )

    run = FixRun(
        project_id=payload.project_id,
        user_id=current_user.id,
        instruction=payload.instruction,
        test_command=payload.test_command,
        max_iterations=payload.max_iterations,
        status="queued",
    )

    db.add(run)
    db.commit()
    db.refresh(run)

    background_tasks.add_task(_run_in_background, run.id)

    return run


@router.get("", response_model=list[FixRunOut])
def list_fix_runs(
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[FixRun]:
    project = db.get(Project, project_id)

    if project is None or resolve_project_role(db, project, current_user) is None:
        raise not_found

    return (
        db.query(FixRun)
        .filter(FixRun.project_id == project_id)
        .order_by(FixRun.created_at.desc())
        .all()
    )


@router.get("/{run_id}", response_model=FixRunDetail)
def get_fix_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FixRunDetail:
    run = _accessible_run(db, current_user, run_id)

    iterations = (
        db.query(FixIteration)
        .filter(FixIteration.fix_run_id == run.id)
        .order_by(FixIteration.iteration)
        .all()
    )

    diff = None

    if run.proposed_patch:
        patch = json.loads(run.proposed_patch)
        before = project_files(db, run.project_id)
        after = dict(before)

        for change in patch["changes"]:
            after[change["path"]] = change["content"]

        diff = compute_diff(before, after)

    return FixRunDetail(
        id=run.id,
        project_id=run.project_id,
        instruction=run.instruction,
        test_command=run.test_command,
        status=run.status,
        max_iterations=run.max_iterations,
        summary=run.summary,
        error=run.error,
        created_at=run.created_at,
        updated_at=run.updated_at,
        iterations=[FixIterationOut.model_validate(i) for i in iterations],
        diff=diff,
    )


@router.post("/{run_id}/apply", response_model=FixApplyResponse)
def apply_fix_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FixApplyResponse:
    run = _accessible_run(db, current_user, run_id)

    _writable_project(db, current_user, run.project_id)

    if run.status != "awaiting_approval" or not run.proposed_patch:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Run {run.id} is '{run.status}' and has no patch awaiting "
                "approval."
            ),
        )

    touched = apply_patch(db, run)

    return FixApplyResponse(
        run_id=run.id,
        applied_paths=touched,
        message=f"Applied {len(touched)} file change(s).",
    )


@router.post("/{run_id}/cancel", response_model=FixRunOut)
def cancel_fix_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FixRun:
    run = _accessible_run(db, current_user, run_id)

    if run.status in ("succeeded", "failed", "cancelled"):
        raise HTTPException(
            status_code=409, detail=f"Run {run.id} has already finished."
        )

    # The loop checks this flag between iterations rather than being killed
    # mid-flight, so a cancel never interrupts a container that is already
    # running - it just stops the next one from starting.
    run.status = "cancelled"
    db.commit()
    db.refresh(run)

    return run
