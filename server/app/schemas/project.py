from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    # Optional: a project with no workspace stays private to its owner, which
    # is how every project created before workspaces existed behaves.
    workspace_id: int | None = None


class ProjectOut(BaseModel):
    id: int
    name: str
    owner_id: int
    workspace_id: int | None = None

    model_config = ConfigDict(from_attributes=True)
