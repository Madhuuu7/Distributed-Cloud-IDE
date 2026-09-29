"""Workspace-aware authorisation.

The existing API answered one question: does this user own this row? Workspaces
add a second path to the same resource, so access is now resolved to an
*effective role* and every endpoint states the minimum role it needs.

The two status codes mean different things and the distinction is deliberate:

``404`` - the caller has no relationship to this resource. Returning ``403``
here would confirm that a project with that id exists, which is a disclosure to
someone with no business knowing it.

``403`` - the caller is in the workspace but their role is too low. They
already know the resource exists, so naming the real reason leaks nothing and
saves them guessing.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import AI_RATE_LIMIT_PER_MINUTE
from app.core.deps import get_current_user, get_db
from app.models.project import Project
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, role_at_least

not_found = HTTPException(status_code=404, detail="Not found")


def _forbidden(required: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"This action requires the '{required}' role or higher.",
    )


def membership_role(db: Session, workspace_id: int, user_id: int) -> str | None:
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )

    return member.role if member else None


def resolve_project_role(db: Session, project: Project, user: User) -> str | None:
    """The caller's effective role on a project, or ``None`` if unreachable.

    Direct ownership outranks workspace membership. Someone who created a
    project and later added it to a workspace as a viewer has not thereby
    demoted themselves out of their own work.
    """
    if project.owner_id == user.id:
        return "owner"

    if project.workspace_id is None:
        return None

    return membership_role(db, project.workspace_id, user.id)


class ProjectAccess:
    """Dependency factory: load a project, enforcing a minimum role."""

    def __init__(self, required: str = "viewer") -> None:
        self.required = required

    def __call__(
        self,
        project_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ) -> Project:
        project = db.get(Project, project_id)

        if project is None:
            raise not_found

        role = resolve_project_role(db, project, current_user)

        if role is None:
            raise not_found

        if not role_at_least(role, self.required):
            raise _forbidden(self.required)

        return project


# Reading a project, running its code, and asking the AI about it are three
# different privilege levels, so they get three dependencies rather than one
# check repeated with different arguments at each call site.
readable_project = ProjectAccess("viewer")
writable_project = ProjectAccess("editor")


class WorkspaceAccess:
    def __init__(self, required: str = "viewer") -> None:
        self.required = required

    def __call__(
        self,
        workspace_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ) -> Workspace:
        workspace = db.get(Workspace, workspace_id)

        if workspace is None:
            raise not_found

        role = membership_role(db, workspace_id, current_user.id)

        if role is None:
            raise not_found

        if not role_at_least(role, self.required):
            raise _forbidden(self.required)

        return workspace


readable_workspace = WorkspaceAccess("viewer")
writable_workspace = WorkspaceAccess("editor")
owned_workspace = WorkspaceAccess("owner")


class RateLimiter:
    """A per-user sliding window over AI calls.

    An AI endpoint with no limit sits in front of a metered API, which means a
    retry loop in somebody's client code is an unbounded bill. This is the
    cheapest thing that closes that hole.

    In-process, like the prompt cache, so the effective limit is per worker.
    That is fine for a ceiling whose job is to stop runaway loops rather than
    to meter precisely.
    """

    def __init__(self, max_calls: int, window_seconds: int = 60) -> None:
        self._calls: dict[int, deque[float]] = defaultdict(deque)
        self._max_calls = max_calls
        self._window = window_seconds
        self._lock = threading.Lock()

    def check(self, user_id: int) -> None:
        now = time.time()

        with self._lock:
            timestamps = self._calls[user_id]

            while timestamps and now - timestamps[0] > self._window:
                timestamps.popleft()

            if len(timestamps) >= self._max_calls:
                retry_after = int(self._window - (now - timestamps[0])) + 1

                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"AI rate limit reached "
                        f"({self._max_calls} requests per minute)."
                    ),
                    headers={"Retry-After": str(retry_after)},
                )

            timestamps.append(now)


ai_rate_limiter = RateLimiter(AI_RATE_LIMIT_PER_MINUTE)


def enforce_ai_rate_limit(current_user: User = Depends(get_current_user)) -> User:
    ai_rate_limiter.check(current_user.id)

    return current_user
