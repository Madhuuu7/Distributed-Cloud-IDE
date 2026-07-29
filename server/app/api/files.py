from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.file import FileNode
from app.schemas.file import FileCreate, FileOut, FileUpdate

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get('/{project_id}/files', response_model=list[FileOut])
def list_files(project_id: int, db: Session = Depends(get_db)) -> list[FileOut]:
    files = db.query(FileNode).filter(FileNode.project_id == project_id).all()
    return files


@router.post('/{project_id}/files', response_model=FileOut)
def create_file(project_id: int, payload: FileCreate, db: Session = Depends(get_db)) -> FileOut:
    file_node = FileNode(
        project_id=project_id,
        name=payload.name,
        path=f"/{payload.name}",
        content=payload.content or "",
        language="text",
    )
    db.add(file_node)
    db.commit()
    db.refresh(file_node)
    return file_node

@router.get("/file/{file_id}", response_model=FileOut)
def get_file(file_id: int, db: Session = Depends(get_db)) -> FileOut:
    file = db.query(FileNode).filter(FileNode.id == file_id).first()

    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    return file


@router.put("/file/{file_id}", response_model=FileOut)
def update_file(
    file_id: int,
    payload: FileUpdate,
    db: Session = Depends(get_db),
) -> FileOut:
    file = db.query(FileNode).filter(FileNode.id == file_id).first()

    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    file.content = payload.content

    db.commit()
    db.refresh(file)

    return file
