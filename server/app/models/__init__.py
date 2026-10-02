"""Every model, in one import.

Alembic compares ``Base.metadata`` against the live database to decide what a
migration should contain, and a model it never imported is a table it will
happily propose dropping. Importing them here - rather than relying on a router
to pull each one in - is what makes ``alembic revision --autogenerate`` and the
schema test trustworthy.
"""

from app.models.ai import AIUsage, Conversation, ConversationMessage
from app.models.file import FileNode
from app.models.fix import FixIteration, FixRun
from app.models.project import Project
from app.models.rag import CodeChunk, ProjectIndex
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceMessage

__all__ = [
    "AIUsage",
    "CodeChunk",
    "Conversation",
    "ConversationMessage",
    "FileNode",
    "FixIteration",
    "FixRun",
    "Project",
    "ProjectIndex",
    "User",
    "Workspace",
    "WorkspaceMember",
    "WorkspaceMessage",
]
