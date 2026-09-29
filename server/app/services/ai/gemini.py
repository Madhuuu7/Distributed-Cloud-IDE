"""Google Gemini over its REST API.

Kept here mainly because the free tier makes this project runnable by anyone
who does not want to pay for tokens, and because it *does* have an embeddings
endpoint - which is why it is often the right choice for
``AI_EMBEDDING_PROVIDER`` even when generation comes from somewhere else.

Gemini's wire format differs from the others in three ways worth naming: the
assistant role is called ``model``, the system prompt is a separate
``systemInstruction`` object, and streaming is SSE only when ``alt=sse`` is
passed - otherwise it returns a JSON array that never closes until the end,
which defeats the point.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from app.core.config import (
    AI_REQUEST_TIMEOUT_SECONDS,
    GEMINI_API_KEY,
    GEMINI_EMBEDDING_MODEL,
    GEMINI_MODEL,
)
from app.services.ai.base import (
    Completion,
    Feature,
    LLMProvider,
    Message,
    ProviderError,
    Usage,
)

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(LLMProvider):
    name = "gemini"
    pricing = (0.0, 0.0)  # Free tier by default; override in config if billed.
    embedding_dimensions = 768  # text-embedding-004

    @property
    def is_configured(self) -> bool:
        return bool(GEMINI_API_KEY)

    @property
    def model(self) -> str:
        return GEMINI_MODEL

    def _build_body(
        self,
        messages: list[Message],
        *,
        temperature: float,
        max_tokens: int,
        json_schema: dict | None,
    ) -> dict:
        contents = [
            {
                # Gemini calls the assistant turn "model".
                "role": "model" if m.role == "assistant" else "user",
                "parts": [{"text": m.content}],
            }
            for m in messages
            if m.role != "system"
        ]

        body: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        system = "\n\n".join(m.content for m in messages if m.role == "system")

        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        if json_schema is not None:
            body["generationConfig"]["responseMimeType"] = "application/json"
            body["generationConfig"]["responseSchema"] = _strip_unsupported(json_schema)

        return body

    def complete(
        self,
        messages: list[Message],
        *,
        feature: Feature = "chat",
        temperature: float = 0.2,
        max_tokens: int = 1024,
        json_schema: dict | None = None,
    ) -> Completion:
        if not self.is_configured:
            raise ProviderError("GEMINI_API_KEY is not set.")

        body = self._build_body(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_schema=json_schema,
        )

        try:
            response = httpx.post(
                f"{_BASE_URL}/models/{self.model}:generateContent",
                params={"key": GEMINI_API_KEY},
                json=body,
                timeout=AI_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Gemini request failed: {exc}") from exc

        candidates = payload.get("candidates") or []

        if not candidates:
            # An empty candidate list means the safety filter blocked it.
            reason = payload.get("promptFeedback", {}).get("blockReason", "unknown")
            raise ProviderError(f"Gemini returned no candidates (reason: {reason}).")

        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts)
        usage = payload.get("usageMetadata", {})

        return Completion(
            text=text,
            model=self.model,
            usage=Usage(
                prompt_tokens=usage.get("promptTokenCount", 0),
                completion_tokens=usage.get("candidatesTokenCount", 0),
            ),
            finish_reason=candidates[0].get("finishReason", "stop"),
        )

    def stream(
        self,
        messages: list[Message],
        *,
        feature: Feature = "chat",
        temperature: float = 0.2,
        max_tokens: int = 1024,
        json_schema: dict | None = None,
    ) -> Iterator[str]:
        if not self.is_configured:
            raise ProviderError("GEMINI_API_KEY is not set.")

        body = self._build_body(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_schema=json_schema,
        )

        try:
            with httpx.stream(
                "POST",
                f"{_BASE_URL}/models/{self.model}:streamGenerateContent",
                params={"key": GEMINI_API_KEY, "alt": "sse"},
                json=body,
                timeout=AI_REQUEST_TIMEOUT_SECONDS,
            ) as response:
                response.raise_for_status()

                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue

                    chunk = json.loads(line[5:].strip())

                    for candidate in chunk.get("candidates", []):
                        for part in candidate.get("content", {}).get("parts", []):
                            if part.get("text"):
                                yield part["text"]
        except httpx.HTTPError as exc:
            raise ProviderError(f"Gemini stream failed: {exc}") from exc

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.is_configured:
            raise ProviderError("GEMINI_API_KEY is not set.")

        model_path = f"models/{GEMINI_EMBEDDING_MODEL}"

        # One round trip for the whole batch. Indexing a project means
        # hundreds of chunks, and a request each would be slow enough to make
        # the feature feel broken.
        body = {
            "requests": [
                {
                    "model": model_path,
                    "content": {"parts": [{"text": text}]},
                }
                for text in texts
            ]
        }

        try:
            response = httpx.post(
                f"{_BASE_URL}/{model_path}:batchEmbedContents",
                params={"key": GEMINI_API_KEY},
                json=body,
                timeout=AI_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Gemini embedding failed: {exc}") from exc

        return [item["values"] for item in payload.get("embeddings", [])]


def _strip_unsupported(schema: dict) -> dict:
    """Remove JSON Schema keywords Gemini's subset rejects.

    Gemini accepts an OpenAPI-flavoured subset. ``additionalProperties`` in
    particular is a hard error rather than something it ignores, and our
    schemas carry it because Anthropic's strict mode requires it.
    """
    if not isinstance(schema, dict):
        return schema

    cleaned = {
        key: value
        for key, value in schema.items()
        if key not in {"additionalProperties", "$schema", "title"}
    }

    if "properties" in cleaned:
        cleaned["properties"] = {
            name: _strip_unsupported(value)
            for name, value in cleaned["properties"].items()
        }

    if "items" in cleaned:
        cleaned["items"] = _strip_unsupported(cleaned["items"])

    return cleaned
