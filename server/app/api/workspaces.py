"""Shared workspaces: membership, roles, and room chat."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.access import (
    membership_role,
    not_found,
    owned_workspace,
    readable_workspace,
    writable_workspace,
)
from app.core.deps import get_current_user, get_db
from app.models.file import FileNode
from app.models.project import Project
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceMessage
from app.schemas.workspace import (
    MemberInvite,
    MemberOut,
    MemberRoleUpdate,
    MessageCreate,
    MessageOut,
    WorkspaceCreate,
    WorkspaceDetail,
    WorkspaceOut,
)

router = APIRouter()


def _owner_count(db: Session, workspace_id: int) -> int:
    return (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == "owner",
        )
        .count()
    )


@router.get("", response_model=list[WorkspaceOut])
def list_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Workspace]:
    return (
        db.query(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .filter(WorkspaceMember.user_id == current_user.id)
        .order_by(Workspace.created_at.desc())
        .all()
    )


@router.post("", response_model=WorkspaceDetail, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkspaceDetail:
    workspace = Workspace(name=payload.name, description=payload.description)

    db.add(workspace)
    db.flush()

    # The creator is added as a member in the same transaction as the
    # workspace. If this were a second request, a failure between them would
    # leave a workspace nobody - including its creator - could reach.
    db.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=current_user.id,
            role="owner",
        )
    )
    db.commit()
    db.refresh(workspace)

    return WorkspaceDetail(
        id=workspace.id,
        name=workspace.name,
        description=workspace.description,
        created_at=workspace.created_at,
        role="owner",
        member_count=1,
        project_count=0,
    )


@router.get("/{workspace_id}", response_model=WorkspaceDetail)
def get_workspace(
    workspace: Workspace = Depends(readable_workspace),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkspaceDetail:
    role = membership_role(db, workspace.id, current_user.id)

    return WorkspaceDetail(
        id=workspace.id,
        name=workspace.name,
        description=workspace.description,
        created_at=workspace.created_at,
        role=role,
        member_count=(
            db.query(WorkspaceMember)
            .filter(WorkspaceMember.workspace_id == workspace.id)
            .count()
        ),
        project_count=(
            db.query(Project)
            .filter(Project.workspace_id == workspace.id)
            .count()
        ),
    )


@router.delete("/{workspace_id}")
def delete_workspace(
    workspace: Workspace = Depends(owned_workspace),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    # Projects are detached, not deleted. A workspace is a way of sharing
    # work, so dissolving it should return each project to its owner rather
    # than destroy everyone's code.
    db.query(Project).filter(Project.workspace_id == workspace.id).update(
        {Project.workspace_id: None}
    )
    db.query(WorkspaceMessage).filter(
        WorkspaceMessage.workspace_id == workspace.id
    ).delete()
    db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace.id
    ).delete()
    db.delete(workspace)
    db.commit()

    return {"message": "Workspace deleted; its projects were returned to their owners"}


@router.get("/{workspace_id}/members", response_model=list[MemberOut])
def list_members(
    workspace: Workspace = Depends(readable_workspace),
    db: Session = Depends(get_db),
) -> list[MemberOut]:
    rows = (
        db.query(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .filter(WorkspaceMember.workspace_id == workspace.id)
        .order_by(WorkspaceMember.created_at)
        .all()
    )

    return [
        MemberOut(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=member.role,
            joined_at=member.created_at,
        )
        for member, user in rows
    ]


@router.post(
    "/{workspace_id}/members",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
)
def invite_member(
    payload: MemberInvite,
    workspace: Workspace = Depends(owned_workspace),
    db: Session = Depends(get_db),
) -> MemberOut:
    user = db.query(User).filter(User.email == payload.email).first()

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="No user with that email address has signed up.",
        )

    existing = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user.id,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="That user is already a member of this workspace.",
        )

    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=user.id,
        role=payload.role,
    )

    db.add(member)
    db.commit()
    db.refresh(member)

    return MemberOut(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=member.role,
        joined_at=member.created_at,
    )


@router.patch("/{workspace_id}/members/{user_id}", response_model=MemberOut)
def update_member_role(
    user_id: int,
    payload: MemberRoleUpdate,
    workspace: Workspace = Depends(owned_workspace),
    db: Session = Depends(get_db),
) -> MemberOut:
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )

    if member is None:
        raise not_found

    # Demoting the last owner would leave a workspace nobody can administer -
    # no invites, no role changes, no deletion. There is no recovery path from
    # that state short of database surgery.
    if (
        member.role == "owner"
        and payload.role != "owner"
        and _owner_count(db, workspace.id) == 1
    ):
        raise HTTPException(
            status_code=409,
            detail="A workspace must keep at least one owner.",
        )

    member.role = payload.role
    db.commit()
    db.refresh(member)

    user = db.get(User, user_id)

    return MemberOut(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=member.role,
        joined_at=member.created_at,
    )


@router.delete("/{workspace_id}/members/{user_id}")
def remove_member(
    user_id: int,
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Remove a member, or leave the workspace yourself.

    Not declared with the owner dependency because leaving is something any
    member may do - requiring the owner role to leave would trap people in
    workspaces they were added to.
    """
    caller_role = membership_role(db, workspace_id, current_user.id)

    if caller_role is None:
        raise not_found

    is_self = user_id == current_user.id

    if not is_self and caller_role != "owner":
        raise HTTPException(
            status_code=403,
            detail="Only an owner can remove another member.",
        )

    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )

    if member is None:
        raise not_found

    if member.role == "owner" and _owner_count(db, workspace_id) == 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "A workspace must keep at least one owner. "
                "Promote someone else first."
            ),
        )

    db.delete(member)
    db.commit()

    return {"message": "Left the workspace" if is_self else "Member removed"}


@router.get("/{workspace_id}/messages", response_model=list[MessageOut])
def list_messages(
    workspace: Workspace = Depends(readable_workspace),
    db: Session = Depends(get_db),
    limit: int = 100,
) -> list[WorkspaceMessage]:
    messages = (
        db.query(WorkspaceMessage)
        .filter(WorkspaceMessage.workspace_id == workspace.id)
        .order_by(WorkspaceMessage.id.desc())
        .limit(min(limit, 500))
        .all()
    )

    # Queried newest-first so the limit keeps the most recent messages, then
    # reversed so the client receives them in reading order.
    return list(reversed(messages))


@router.post(
    "/{workspace_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
def post_message(
    payload: MessageCreate,
    workspace: Workspace = Depends(writable_workspace),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkspaceMessage:
    if payload.file_id is not None:
        file_node = db.get(FileNode, payload.file_id)

        if file_node is None:
            raise not_found

        project = db.get(Project, file_node.project_id)

        # A comment may only be anchored to a file in this workspace.
        # Otherwise a member could pin a comment onto a file they cannot read
        # and learn its id is valid.
        if project is None or project.workspace_id != workspace.id:
            raise not_found

    message = WorkspaceMessage(
        workspace_id=workspace.id,
        user_id=current_user.id,
        body=payload.body,
        file_id=payload.file_id,
        line=payload.line,
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return message
