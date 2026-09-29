from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)

credentials_error = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the bearer token into a User, or fail with 401."""
    if credentials is None:
        raise credentials_error

    try:
        subject = decode_access_token(credentials.credentials)
    except JWTError:
        raise credentials_error

    if not subject:
        raise credentials_error

    try:
        user_id = int(subject)
    except ValueError:
        raise credentials_error

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise credentials_error

    return user


def get_accessible_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Load a project the caller can read, or fail with 404.

    "Can read" now means owned **or** shared through a workspace. The import is
    function-local because ``app.core.access`` imports this module, and the
    role logic belongs next to the rest of the authorisation rules rather than
    duplicated here.
    """
    from app.core.access import resolve_project_role
    from app.models.project import Project

    project = db.get(Project, project_id)

    if project is None or resolve_project_role(db, project, current_user) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return project


def require_project_editor(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Load a project the caller may modify.

    Separate from the read dependency so a ``viewer`` gets a 403 that explains
    the problem, rather than a 404 that implies the project vanished.
    """
    from app.core.access import resolve_project_role
    from app.models.project import Project
    from app.models.workspace import role_at_least

    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    role = resolve_project_role(db, project, current_user)

    if role is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if not role_at_least(role, "editor"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires the 'editor' role or higher.",
        )

    return project


# The original name, kept so existing call sites and tests keep working.
get_owned_project = get_accessible_project


def _load_file(db: Session, file_id: int, current_user: User, *, write: bool):
    from app.core.access import resolve_project_role
    from app.models.file import FileNode
    from app.models.project import Project
    from app.models.workspace import role_at_least

    file_node = db.get(FileNode, file_id)

    if file_node is None:
        raise HTTPException(status_code=404, detail="File not found")

    project = db.get(Project, file_node.project_id)

    if project is None:
        raise HTTPException(status_code=404, detail="File not found")

    role = resolve_project_role(db, project, current_user)

    if role is None:
        raise HTTPException(status_code=404, detail="File not found")

    if write and not role_at_least(role, "editor"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires the 'editor' role or higher.",
        )

    return file_node


def get_owned_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Load a file the caller can read, or fail with 404."""
    return _load_file(db, file_id, current_user, write=False)


def get_writable_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Load a file the caller may modify, or fail with 404/403."""
    return _load_file(db, file_id, current_user, write=True)
