from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.execute import ExecuteRequest, ExecuteResponse
from app.services.execution_service import (
    SandboxUnavailable,
    UnsupportedLanguage,
    run_code,
    supported_languages,
)

router = APIRouter()


@router.get("/languages")
def list_languages(_: User = Depends(get_current_user)) -> dict[str, list[str]]:
    return {"languages": supported_languages()}


@router.post("", response_model=ExecuteResponse)
def execute_code(
    payload: ExecuteRequest,
    _: User = Depends(get_current_user),
) -> ExecuteResponse:
    try:
        result = run_code(payload.language, payload.code)
    except UnsupportedLanguage as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SandboxUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return ExecuteResponse(
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        duration_ms=result.duration_ms,
        timed_out=result.timed_out,
        backend=result.backend,
    )
