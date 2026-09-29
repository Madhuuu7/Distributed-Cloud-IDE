from pydantic import BaseModel, ConfigDict


class FileCreate(BaseModel):
    name: str
    content: str | None = None


class FileUpdate(BaseModel):
    content: str


class FileOut(BaseModel):
    id: int
    project_id: int
    name: str
    path: str
    content: str
    language: str

    model_config = ConfigDict(from_attributes=True)