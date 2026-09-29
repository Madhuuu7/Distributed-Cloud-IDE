from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, get_owned_project
from app.models.file import FileNode
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectOut

router = APIRouter()


@router.get("", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProjectOut]:
    return (
        db.query(Project)
        .filter(Project.owner_id == current_user.id)
        .order_by(Project.created_at.desc())
        .all()
    )


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectOut:
    project = Project(name=payload.name, owner_id=current_user.id)

    db.add(project)
    db.commit()
    db.refresh(project)

    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project: Project = Depends(get_owned_project)) -> ProjectOut:
    return project


@router.delete("/{project_id}")
def delete_project(
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    # Files have no ON DELETE rule, so clear them explicitly to avoid orphans.
    db.query(FileNode).filter(FileNode.project_id == project.id).delete()
    db.delete(project)
    db.commit()

    return {"message": "Project deleted successfully"}
