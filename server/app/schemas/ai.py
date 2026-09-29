from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["info", "minor", "major", "critical"]


class ProviderOut(BaseModel):
    name: str
    model: str
    configured: bool
    active: bool
    embedding_active: bool
    embedding_dimensions: int
    price_per_mtok: dict[str, float]


class Citation(BaseModel):
    """Where an answer came from.

    Returned with every grounded reply so a claim can be checked against the
    code rather than taken on trust.
    """

    path: str
    symbol: str | None = None
    start_line: int
    end_line: int
    score: float


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: int | None = None
    project_id: int | None = None
    use_rag: bool = True


class ChatResponse(BaseModel):
    conversation_id: int
    message: str
    citations: list[Citation] = []
    provider: str
    model: str
    cached: bool
    tokens: int
    cost_usd: float
    latency_ms: int


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    project_id: int | None
    created_at: datetime
    updated_at: datetime


class ConversationMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[ConversationMessageOut]


class ExplainRequest(BaseModel):
    file_id: int
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class ExplainResponse(BaseModel):
    explanation: str
    path: str
    start_line: int
    end_line: int
    cached: bool
    cost_usd: float


class ReviewRequest(BaseModel):
    project_id: int
    file_ids: list[int] | None = None


class Finding(BaseModel):
    path: str
    line: int = Field(ge=1)
    severity: Severity
    message: str
    suggestion: str | None = None


class ReviewResponse(BaseModel):
    findings: list[Finding]
    files_reviewed: int
    cached: bool
    cost_usd: float


class DailyUsage(BaseModel):
    day: date
    calls: int
    tokens: int
    cost_usd: float


class FeatureUsage(BaseModel):
    feature: str
    calls: int
    tokens: int
    cost_usd: float


class UsageResponse(BaseModel):
    days: int
    total_calls: int
    total_tokens: int
    total_cost_usd: float
    # What the cache saved, priced at the current rate. The point of the
    # dashboard is to make this number visible.
    cache_hit_rate: float
    estimated_savings_usd: float
    by_day: list[DailyUsage]
    by_feature: list[FeatureUsage]
