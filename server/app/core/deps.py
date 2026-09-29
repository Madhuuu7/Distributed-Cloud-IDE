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


def get_owned_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Load a project the caller owns, or fail with 404."""
    from app.models.project import Project

    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.owner_id == current_user.id)
        .first()
    )

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return project


def get_owned_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Load a file inside a project the caller owns, or fail with 404."""
    from app.models.file import FileNode
    from app.models.project import Project

    file_node = (
        db.query(FileNode)
        .join(Project, Project.id == FileNode.project_id)
        .filter(FileNode.id == file_id, Project.owner_id == current_user.id)
        .first()
    )

    if not file_node:
        raise HTTPException(status_code=404, detail="File not found")

    return file_node
