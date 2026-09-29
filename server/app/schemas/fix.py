from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import FIX_ITERATION_CEILING, FIX_MAX_ITERATIONS

FixStatus = Literal[
    "queued",
    "running",
    "awaiting_approval",
    "succeeded",
    "failed",
    "cancelled",
]


class FixRunCreate(BaseModel):
    project_id: int
    instruction: str = Field(min_length=1, max_length=4000)
    # Left unset, the language's default stdlib test runner is used. The
    # sandbox has no network, so nothing can be installed into it - a command
    # that needs pytest will not work.
    test_command: str | None = Field(default=None, max_length=500)
    max_iterations: int = Field(
        default=FIX_MAX_ITERATIONS, ge=1, le=FIX_ITERATION_CEILING
    )


class FixIterationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    iteration: int
    reasoning: str | None
    stdout: str | None
    stderr: str | None
    exit_code: int | None
    passed: bool
    created_at: datetime


class FixRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    instruction: str
    test_command: str | None
    status: FixStatus
    max_iterations: int
    summary: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class FixRunDetail(FixRunOut):
    # Every attempt, including the failures. The sequence of wrong answers and
    # the failures that corrected them is the story of what the agent did.
    iterations: list[FixIterationOut]
    # Derived server-side from the before/after file contents, so it cannot be
    # a malformed diff the model emitted.
    diff: str | None


class FixApplyResponse(BaseModel):
    run_id: int
    applied_paths: list[str]
    message: str
