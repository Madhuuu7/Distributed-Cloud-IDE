from pydantic import BaseModel


class FileCreate(BaseModel):
    name: str
    content: str | None = None


class FileOut(BaseModel):
    id: int
    project_id: int
    name: str
    path: str
    content: str
    language: str

    class Config:
        from_attributes = True
