import subprocess
import tempfile
import os

from fastapi import APIRouter
from app.schemas.execute import ExecuteRequest, ExecuteResponse

router = APIRouter()


@router.post("", response_model=ExecuteResponse)
def execute_code(payload: ExecuteRequest):
    if payload.language != "python":
        return ExecuteResponse(
            output="Only Python execution is supported right now."
        )

    with tempfile.NamedTemporaryFile(
        suffix=".py",
        delete=False,
        mode="w",
        encoding="utf-8",
    ) as temp_file:
        temp_file.write(payload.code)
        temp_path = temp_file.name

    try:
        result = subprocess.run(
            ["python", temp_path],
            capture_output=True,
            text=True,
            timeout=5,
        )

        output = result.stdout

        if result.stderr:
            output += result.stderr

    except Exception as e:
        output = str(e)

    finally:
        os.remove(temp_path)

    return ExecuteResponse(output=output)