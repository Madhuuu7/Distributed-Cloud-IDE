from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.access import membership_role
from app.core.deps import get_current_user, get_db, get_owned_project
from app.models.file import FileNode
from app.models.project import Project
from app.models.user import User
from app.models.workspace import WorkspaceMember, role_at_least
from app.schemas.project import ProjectCreate, ProjectOut

router = APIRouter()


@router.get("", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProjectOut]:
    # Everything the caller owns, plus everything shared with them through a
    # workspace they belong to.
    shared_workspace_ids = [
        row.workspace_id
        for row in db.query(WorkspaceMember.workspace_id)
        .filter(WorkspaceMember.user_id == current_user.id)
        .all()
    ]

    condition = Project.owner_id == current_user.id

    if shared_workspace_ids:
        condition = or_(
            condition, Project.workspace_id.in_(shared_workspace_ids)
        )

    return (
        db.query(Project)
        .filter(condition)
        .order_by(Project.created_at.desc())
        .all()
    )


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectOut:
    if payload.workspace_id is not None:
        role = membership_role(db, payload.workspace_id, current_user.id)

        if role is None:
            # 404, not 403: the caller has no relationship to this workspace,
            # so its existence is not theirs to learn.
            raise HTTPException(status_code=404, detail="Workspace not found")

        if not role_at_least(role, "editor"):
            raise HTTPException(
                status_code=403,
                detail="Creating a project requires the 'editor' role or higher.",
            )

    project = Project(
        name=payload.name,
        owner_id=current_user.id,
        workspace_id=payload.workspace_id,
    )

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
