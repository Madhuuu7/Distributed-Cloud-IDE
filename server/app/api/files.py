from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_owned_file, get_owned_project
from app.models.file import FileNode
from app.models.project import Project
from app.schemas.file import FileCreate, FileOut, FileUpdate
from app.services.languages import detect_language

router = APIRouter()


@router.get("/{project_id}/files", response_model=list[FileOut])
def list_files(
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
) -> list[FileOut]:
    return (
        db.query(FileNode)
        .filter(FileNode.project_id == project.id)
        .order_by(FileNode.name)
        .all()
    )


@router.post("/{project_id}/files", response_model=FileOut, status_code=status.HTTP_201_CREATED)
def create_file(
    payload: FileCreate,
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
) -> FileOut:
    name = payload.name.strip().strip("/")

    if not name:
        raise HTTPException(status_code=400, detail="File name is required")

    existing = (
        db.query(FileNode)
        .filter(FileNode.project_id == project.id, FileNode.name == name)
        .first()
    )

    if existing:
        raise HTTPException(status_code=409, detail="A file with that name already exists")

    file_node = FileNode(
        project_id=project.id,
        name=name,
        path=f"/{name}",
        content=payload.content or "",
        language=detect_language(name),
    )

    db.add(file_node)
    db.commit()
    db.refresh(file_node)

    return file_node


@router.get("/file/{file_id}", response_model=FileOut)
def get_file(file_node: FileNode = Depends(get_owned_file)) -> FileOut:
    return file_node


@router.put("/file/{file_id}", response_model=FileOut)
def update_file(
    payload: FileUpdate,
    file_node: FileNode = Depends(get_owned_file),
    db: Session = Depends(get_db),
) -> FileOut:
    file_node.content = payload.content

    db.commit()
    db.refresh(file_node)

    return file_node


@router.delete("/file/{file_id}")
def delete_file(
    file_node: FileNode = Depends(get_owned_file),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    db.delete(file_node)
    db.commit()

    return {"message": "File deleted successfully"}
