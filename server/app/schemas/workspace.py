from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Role = Literal["viewer", "editor", "owner"]


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime


class WorkspaceDetail(WorkspaceOut):
    # The caller's own role travels with the workspace so a client can hide
    # controls it would only be rejected for using.
    role: Role
    member_count: int
    project_count: int


class MemberInvite(BaseModel):
    email: EmailStr
    role: Role = "editor"


class MemberRoleUpdate(BaseModel):
    role: Role


class MemberOut(BaseModel):
    user_id: int
    email: str
    full_name: str | None
    role: Role
    joined_at: datetime


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=8000)
    file_id: int | None = None
    line: int | None = Field(default=None, ge=1)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    user_id: int
    body: str
    file_id: int | None
    line: int | None
    created_at: datetime
