from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class IndexStatus(BaseModel):
    project_id: int
    status: Literal["empty", "building", "ready", "failed"]
    chunk_count: int
    embedding_model: str | None
    dimensions: int | None
    indexed_at: datetime | None
    # True when files changed after the index was built. Exposed rather than
    # silently reindexed so the client can decide whether to pay for a refresh.
    stale: bool
    error: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    project_id: int
    k: int = Field(default=6, ge=1, le=50)


class SearchResult(BaseModel):
    path: str
    symbol: str | None
    language: str
    start_line: int
    end_line: int
    text: str
    score: float
    # Both component scores are surfaced so a surprising ranking can be
    # explained instead of argued with.
    keyword_score: float
    vector_score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    searched_chunks: int
