"""The AI teammate: chat, explain, review, and the cost dashboard."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.access import enforce_ai_rate_limit, not_found, resolve_project_role
from app.core.config import AI_MAX_TOKENS
from app.core.deps import get_current_user, get_db
from app.models.ai import AIUsage, Conversation, ConversationMessage
from app.models.file import FileNode
from app.models.project import Project
from app.models.user import User
from app.schemas.ai import (
    ChatRequest,
    ChatResponse,
    Citation,
    ConversationDetail,
    ConversationOut,
    DailyUsage,
    ExplainRequest,
    ExplainResponse,
    FeatureUsage,
    Finding,
    ProviderOut,
    ReviewRequest,
    ReviewResponse,
    UsageResponse,
)
from app.services.ai import Message, ProviderError, describe_providers, generate
from app.services.ai.cache import prompt_cache
from app.services.ai.prompts import (
    CHAT_SYSTEM,
    EXPLAIN_SYSTEM,
    REVIEW_SCHEMA,
    REVIEW_SYSTEM,
    build_chat_prompt,
    pack_context,
)
from app.services.ai.registry import GenerationResult, get_provider
from app.services.rag.search import search

logger = logging.getLogger(__name__)

router = APIRouter()


def _record_usage(
    db: Session, user: User, result: GenerationResult
) -> None:
    """Write the audit row for one model call.

    Called for cache hits too, with zero cost. Skipping them would make the
    hit rate unknowable after the fact, and the hit rate is the number that
    justifies the cache existing.
    """
    db.add(
        AIUsage(
            user_id=user.id,
            feature=result.feature,
            provider=result.provider,
            model=result.completion.model,
            prompt_tokens=result.completion.usage.prompt_tokens,
            completion_tokens=result.completion.usage.completion_tokens,
            cost_usd=result.cost_usd,
            latency_ms=result.latency_ms,
            cached=result.cached,
        )
    )
    db.commit()


def _readable_project(db: Session, user: User, project_id: int) -> Project:
    project = db.get(Project, project_id)

    if project is None or resolve_project_role(db, project, user) is None:
        raise not_found

    return project


@router.get("/providers", response_model=list[ProviderOut])
def list_providers() -> list[ProviderOut]:
    return [ProviderOut(**item) for item in describe_providers()]


def _retrieve(
    db: Session, user: User, project_id: int | None, question: str
) -> tuple[str, list[Citation]]:
    if project_id is None:
        return "", []

    _readable_project(db, user, project_id)

    hits = search(db, project_id=project_id, query=question)

    citations = [
        Citation(
            path=hit.chunk.path,
            symbol=hit.chunk.symbol,
            start_line=hit.chunk.start_line,
            end_line=hit.chunk.end_line,
            score=round(hit.score, 4),
        )
        for hit in hits
    ]

    return pack_context(hits), citations


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(enforce_ai_rate_limit),
) -> ChatResponse:
    conversation = _resolve_conversation(db, current_user, payload)

    context, citations = (
        _retrieve(db, current_user, payload.project_id, payload.message)
        if payload.use_rag
        else ("", [])
    )

    # Prior turns are replayed so follow-ups like "why?" resolve. Capped at the
    # last 10 because an unbounded history silently grows the cost of every
    # subsequent message in a long conversation.
    history = (
        db.query(ConversationMessage)
        .filter(ConversationMessage.conversation_id == conversation.id)
        .order_by(ConversationMessage.id.desc())
        .limit(10)
        .all()
    )

    messages = [Message("system", CHAT_SYSTEM)]
    messages.extend(
        Message(m.role, m.content) for m in reversed(history)
    )
    messages.append(Message("user", build_chat_prompt(payload.message, context)))

    try:
        result = generate(messages, feature="chat", max_tokens=AI_MAX_TOKENS)
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    db.add(
        ConversationMessage(
            conversation_id=conversation.id,
            role="user",
            content=payload.message,
        )
    )
    db.add(
        ConversationMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=result.text,
            citations=json.dumps([c.model_dump() for c in citations]),
        )
    )
    db.commit()

    _record_usage(db, current_user, result)

    return ChatResponse(
        conversation_id=conversation.id,
        message=result.text,
        citations=citations,
        provider=result.provider,
        model=result.completion.model,
        cached=result.cached,
        tokens=result.completion.usage.total_tokens,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
    )


@router.post("/chat/stream")
def chat_stream(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(enforce_ai_rate_limit),
) -> StreamingResponse:
    """The same call as ``/chat``, delivered as Server-Sent Events.

    Streaming bypasses the prompt cache: a cached reply would arrive as one
    frame, and the point of this endpoint is the incremental delivery. Clients
    that want the cache use ``/chat``.
    """
    conversation = _resolve_conversation(db, current_user, payload)

    context, citations = (
        _retrieve(db, current_user, payload.project_id, payload.message)
        if payload.use_rag
        else ("", [])
    )

    messages = [
        Message("system", CHAT_SYSTEM),
        Message("user", build_chat_prompt(payload.message, context)),
    ]

    provider = get_provider()

    def event_stream():
        # The citations go first so the client can render its sources panel
        # while the answer is still arriving.
        yield _sse(
            "citations",
            {
                "conversation_id": conversation.id,
                "citations": [c.model_dump() for c in citations],
            },
        )

        collected: list[str] = []

        try:
            for delta in provider.stream(
                messages, feature="chat", max_tokens=AI_MAX_TOKENS
            ):
                collected.append(delta)

                yield _sse("token", {"text": delta})
        except ProviderError as exc:
            yield _sse("error", {"detail": str(exc)})

            return

        answer = "".join(collected)

        # Persisted only after the stream completes. A half-received answer
        # stored as if it were whole would corrupt the next turn's history.
        db.add(
            ConversationMessage(
                conversation_id=conversation.id,
                role="user",
                content=payload.message,
            )
        )
        db.add(
            ConversationMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=answer,
                citations=json.dumps([c.model_dump() for c in citations]),
            )
        )
        db.commit()

        yield _sse("done", {"conversation_id": conversation.id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Without this, nginx buffers the whole response and the client
            # sees one burst at the end instead of a stream.
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _resolve_conversation(
    db: Session, user: User, payload: ChatRequest
) -> Conversation:
    if payload.conversation_id is not None:
        conversation = db.get(Conversation, payload.conversation_id)

        if conversation is None or conversation.user_id != user.id:
            raise not_found

        return conversation

    conversation = Conversation(
        user_id=user.id,
        project_id=payload.project_id,
        title=payload.message[:60],
    )

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return conversation


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Conversation]:
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationDetail:
    conversation = db.get(Conversation, conversation_id)

    if conversation is None or conversation.user_id != current_user.id:
        raise not_found

    messages = (
        db.query(ConversationMessage)
        .filter(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.id)
        .all()
    )

    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        project_id=conversation.project_id,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=messages,
    )


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    conversation = db.get(Conversation, conversation_id)

    if conversation is None or conversation.user_id != current_user.id:
        raise not_found

    db.query(ConversationMessage).filter(
        ConversationMessage.conversation_id == conversation_id
    ).delete()
    db.delete(conversation)
    db.commit()

    return {"message": "Conversation deleted successfully"}


@router.post("/explain", response_model=ExplainResponse)
def explain(
    payload: ExplainRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(enforce_ai_rate_limit),
) -> ExplainResponse:
    file_node = db.get(FileNode, payload.file_id)

    if file_node is None:
        raise not_found

    _readable_project(db, current_user, file_node.project_id)

    lines = file_node.content.splitlines()
    start = payload.start_line or 1
    end = payload.end_line or len(lines)

    # Clamped rather than rejected: a client whose editor reports a stale line
    # count should get the explanation it asked for, not a 422.
    start = max(1, min(start, max(1, len(lines))))
    end = max(start, min(end, len(lines)))

    excerpt = "\n".join(lines[start - 1 : end])

    if not excerpt.strip():
        raise HTTPException(status_code=400, detail="That range is empty.")

    messages = [
        Message("system", EXPLAIN_SYSTEM),
        Message(
            "user",
            f"File: {file_node.name} (lines {start}-{end}, {file_node.language})\n\n"
            f"{excerpt}",
        ),
    ]

    try:
        result = generate(messages, feature="explain", max_tokens=AI_MAX_TOKENS)
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    _record_usage(db, current_user, result)

    return ExplainResponse(
        explanation=result.text,
        path=file_node.name,
        start_line=start,
        end_line=end,
        cached=result.cached,
        cost_usd=result.cost_usd,
    )


@router.post("/review", response_model=ReviewResponse)
def review(
    payload: ReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(enforce_ai_rate_limit),
) -> ReviewResponse:
    _readable_project(db, current_user, payload.project_id)

    query = db.query(FileNode).filter(FileNode.project_id == payload.project_id)

    if payload.file_ids:
        query = query.filter(FileNode.id.in_(payload.file_ids))

    files = query.all()

    if not files:
        raise HTTPException(status_code=400, detail="No files to review.")

    # Line numbers are prefixed onto the source because the model is asked to
    # anchor each finding to a line. Without them it counts lines itself, and
    # it miscounts.
    rendered = []

    for file_node in files:
        numbered = "\n".join(
            f"{number:>4} | {line}"
            for number, line in enumerate(file_node.content.splitlines(), start=1)
        )
        rendered.append(f"=== {file_node.name} ===\n{numbered}")

    messages = [
        Message("system", REVIEW_SYSTEM),
        Message("user", "\n\n".join(rendered)),
    ]

    try:
        result = generate(
            messages,
            feature="review",
            max_tokens=AI_MAX_TOKENS,
            json_schema=REVIEW_SCHEMA,
        )
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    _record_usage(db, current_user, result)

    findings = _parse_findings(result.text, {f.name for f in files})

    return ReviewResponse(
        findings=findings,
        files_reviewed=len(files),
        cached=result.cached,
        cost_usd=result.cost_usd,
    )


def _parse_findings(text: str, known_paths: set[str]) -> list[Finding]:
    """Parse the model's JSON, discarding findings that point nowhere.

    Structured output makes malformed JSON unlikely but not impossible - the
    mock provider, a truncated response, or a provider without schema support
    all produce it - so a parse failure degrades to an empty review instead of
    a 500.

    Findings naming a file that was not reviewed are dropped: a citation to a
    file the model invented is worse than no finding, because it looks real.
    """
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Review response was not valid JSON; returning no findings.")

        return []

    findings = []

    for raw in payload.get("findings", []):
        try:
            finding = Finding(**raw)
        except (TypeError, ValueError):
            continue

        if known_paths and finding.path not in known_paths:
            logger.debug("Dropping finding for unknown path %s", finding.path)

            continue

        findings.append(finding)

    return findings


@router.get("/usage", response_model=UsageResponse)
def usage(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UsageResponse:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (
        db.query(AIUsage)
        .filter(AIUsage.user_id == current_user.id, AIUsage.created_at >= since)
        .all()
    )

    by_day: dict = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0})
    by_feature: dict = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0})

    total_tokens = 0
    total_cost = 0.0
    cached_calls = 0
    # What the cached calls would have cost at the rate their tokens imply.
    saved = 0.0

    provider = get_provider()

    for row in rows:
        tokens = row.prompt_tokens + row.completion_tokens
        total_tokens += tokens
        total_cost += row.cost_usd

        if row.cached:
            cached_calls += 1
            saved += (
                row.prompt_tokens * provider.pricing[0]
                + row.completion_tokens * provider.pricing[1]
            ) / 1_000_000

        day = row.created_at.date()
        by_day[day]["calls"] += 1
        by_day[day]["tokens"] += tokens
        by_day[day]["cost"] += row.cost_usd

        by_feature[row.feature]["calls"] += 1
        by_feature[row.feature]["tokens"] += tokens
        by_feature[row.feature]["cost"] += row.cost_usd

    return UsageResponse(
        days=days,
        total_calls=len(rows),
        total_tokens=total_tokens,
        total_cost_usd=round(total_cost, 6),
        cache_hit_rate=round(cached_calls / len(rows), 4) if rows else 0.0,
        estimated_savings_usd=round(saved, 6),
        by_day=[
            DailyUsage(
                day=day,
                calls=values["calls"],
                tokens=values["tokens"],
                cost_usd=round(values["cost"], 6),
            )
            for day, values in sorted(by_day.items())
        ],
        by_feature=[
            FeatureUsage(
                feature=feature,
                calls=values["calls"],
                tokens=values["tokens"],
                cost_usd=round(values["cost"], 6),
            )
            for feature, values in sorted(by_feature.items())
        ],
    )


@router.delete("/cache", status_code=status.HTTP_200_OK)
def clear_cache(_: User = Depends(get_current_user)) -> dict:
    """Drop every cached completion.

    Needed when a prompt changes: the cache keys on the rendered prompt, so an
    edited system prompt produces new keys, but a changed *provider* setting
    with identical prompts would otherwise keep serving the old model's
    answers.
    """
    prompt_cache.clear()

    return {"message": "Prompt cache cleared"}
