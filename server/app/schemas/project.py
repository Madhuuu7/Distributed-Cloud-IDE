from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    name: str


class ProjectOut(BaseModel):
    id: int
    name: str
    owner_id: int

    model_config = ConfigDict(from_attributes=True)
