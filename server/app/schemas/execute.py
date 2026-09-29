from pydantic import BaseModel, Field


class ExecuteRequest(BaseModel):
    language: str = Field(default="python", max_length=32)
    code: str = Field(max_length=200_000)


class ExecuteResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int | None = None
    duration_ms: int
    timed_out: bool
    backend: str

    @property
    def output(self) -> str:
        return self.stdout + self.stderr
