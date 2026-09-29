"""A locally hosted model over Ollama's HTTP API.

The reason to keep this alongside the hosted providers is not cost - the mock
provider already handles "run it for free". It is that Ollama is the only
option here where source code never leaves the machine, which is the difference
between a tool a team can point at a private repository and one it cannot.

Ollama reports token counts as ``prompt_eval_count`` and ``eval_count``, and
omits them entirely on some model builds, so the counts are backfilled with an
estimate and flagged as such by the caller.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from app.core.config import (
    AI_REQUEST_TIMEOUT_SECONDS,
    OLLAMA_BASE_URL,
    OLLAMA_EMBEDDING_MODEL,
    OLLAMA_MODEL,
)
from app.services.ai.base import (
    Completion,
    Feature,
    LLMProvider,
    Message,
    ProviderError,
    Usage,
    estimate_tokens,
)


class OllamaProvider(LLMProvider):
    name = "ollama"
    pricing = (0.0, 0.0)  # Local inference: the cost is electricity, not tokens.
    embedding_dimensions = 768  # nomic-embed-text

    @property
    def is_configured(self) -> bool:
        """Whether an Ollama daemon is actually answering.

        This one pings the server rather than just checking a config value,
        because "Ollama is installed" and "Ollama is running" are different
        states and the second is the one that matters.
        """
        try:
            response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=1.5)

            return response.status_code == 200
        except httpx.HTTPError:
            return False

    @property
    def model(self) -> str:
        return OLLAMA_MODEL

    def _build_body(
        self,
        messages: list[Message],
        *,
        temperature: float,
        max_tokens: int,
        json_schema: dict | None,
        stream: bool,
    ) -> dict:
        body: dict = {
            "model": self.model,
            "messages": [m.as_dict() for m in messages],
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        # Ollama takes the JSON Schema directly as `format`, and constrains
        # decoding to match it - the same guarantee as Anthropic's structured
        # output, by a different name.
        if json_schema is not None:
            body["format"] = json_schema

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
        body = self._build_body(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_schema=json_schema,
            stream=False,
        )

        try:
            response = httpx.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json=body,
                timeout=AI_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Ollama request failed: {exc}. Is `ollama serve` running?"
            ) from exc

        text = payload.get("message", {}).get("content", "")
        prompt = "\n".join(m.content for m in messages)

        return Completion(
            text=text,
            model=payload.get("model", self.model),
            usage=Usage(
                prompt_tokens=payload.get("prompt_eval_count")
                or estimate_tokens(prompt),
                completion_tokens=payload.get("eval_count") or estimate_tokens(text),
            ),
            finish_reason=payload.get("done_reason", "stop"),
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
        body = self._build_body(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_schema=json_schema,
            stream=True,
        )

        try:
            with httpx.stream(
                "POST",
                f"{OLLAMA_BASE_URL}/api/chat",
                json=body,
                timeout=AI_REQUEST_TIMEOUT_SECONDS,
            ) as response:
                response.raise_for_status()

                # Newline-delimited JSON, not SSE - no `data:` prefix to strip.
                for line in response.iter_lines():
                    if not line.strip():
                        continue

                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content")

                    if content:
                        yield content
        except httpx.HTTPError as exc:
            raise ProviderError(f"Ollama stream failed: {exc}") from exc

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = httpx.post(
                f"{OLLAMA_BASE_URL}/api/embed",
                json={"model": OLLAMA_EMBEDDING_MODEL, "input": texts},
                timeout=AI_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Ollama embedding failed: {exc}. "
                f"Pull the model first: ollama pull {OLLAMA_EMBEDDING_MODEL}"
            ) from exc

        return payload.get("embeddings", [])
