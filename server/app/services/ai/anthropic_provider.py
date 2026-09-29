"""Claude, through the official Anthropic SDK.

Three things about this provider are easy to get wrong and are deliberate here:

1. **No ``temperature``.** Claude Opus 5 removed the sampling parameters; sending
   ``temperature`` returns a 400. The argument stays in the interface because
   Gemini and Ollama still honour it, and it is dropped here on purpose.
2. **Structured output, not prompt-begging.** When a caller needs JSON it passes
   a schema, and the request carries ``output_config.format``. The first content
   block is then guaranteed to be valid JSON, so no regex is needed to dig a
   code fence out of prose.
3. **``refusal`` is a 200, not an exception.** Safety classifiers can decline a
   request and still return HTTP 200 with ``stop_reason == "refusal"``. Reading
   ``.content`` without checking first yields a confusing empty answer.
"""

from __future__ import annotations

from collections.abc import Iterator

from app.core.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    AI_PRICE_COMPLETION_PER_MTOK,
    AI_PRICE_PROMPT_PER_MTOK,
)
from app.services.ai.base import (
    Completion,
    Feature,
    LLMProvider,
    Message,
    ProviderError,
    Usage,
)

# Published rates for claude-opus-5 in USD per million tokens. Both are
# overridable from the environment so the cost dashboard stays accurate when
# the price list changes or a different model is configured.
_DEFAULT_PRICING = (5.0, 25.0)

# Effort trades thinking depth against tokens and latency. Interactive features
# get the cheap end; the fix loop is the one place where being right matters
# more than being quick.
_EFFORT_BY_FEATURE: dict[str, str] = {
    "chat": "low",
    "explain": "low",
    "search": "low",
    "review": "high",
    "fix": "high",
}


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    pricing = _DEFAULT_PRICING

    def __init__(self) -> None:
        self._client = None

        if AI_PRICE_PROMPT_PER_MTOK is not None:
            self.pricing = (
                AI_PRICE_PROMPT_PER_MTOK,
                AI_PRICE_COMPLETION_PER_MTOK or _DEFAULT_PRICING[1],
            )

    @property
    def is_configured(self) -> bool:
        if not ANTHROPIC_API_KEY:
            return False

        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False

        return True

    @property
    def model(self) -> str:
        return ANTHROPIC_MODEL

    def _get_client(self):
        """Build the SDK client lazily.

        Constructing it at import time would make the whole application fail to
        start when the key is absent, which defeats the point of having a mock
        provider as the default.
        """
        if self._client is not None:
            return self._client

        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - depends on install
            raise ProviderError(
                "The 'anthropic' package is not installed. "
                "Run: pip install anthropic"
            ) from exc

        if not ANTHROPIC_API_KEY:
            raise ProviderError("ANTHROPIC_API_KEY is not set.")

        self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        return self._client

    def _build_request(
        self,
        messages: list[Message],
        *,
        feature: Feature,
        max_tokens: int,
        json_schema: dict | None,
    ) -> dict:
        # Claude takes the system prompt as a separate top-level field rather
        # than as a message, so it is split out here.
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        turns = [m.as_dict() for m in messages if m.role != "system"]

        request: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": turns,
            "output_config": {"effort": _EFFORT_BY_FEATURE.get(feature, "low")},
        }

        if system:
            request["system"] = system

        if json_schema is not None:
            request["output_config"]["format"] = {
                "type": "json_schema",
                "schema": json_schema,
            }

        return request

    def complete(
        self,
        messages: list[Message],
        *,
        feature: Feature = "chat",
        temperature: float = 0.2,
        max_tokens: int = 1024,
        json_schema: dict | None = None,
    ) -> Completion:
        client = self._get_client()
        request = self._build_request(
            messages,
            feature=feature,
            max_tokens=max_tokens,
            json_schema=json_schema,
        )

        try:
            response = client.messages.create(**request)
        except Exception as exc:  # SDK raises a family of typed errors
            raise ProviderError(f"Anthropic request failed: {exc}") from exc

        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            raise ProviderError(
                f"Claude declined this request (category: {category or 'unknown'})."
            )

        text = "".join(
            block.text for block in response.content if block.type == "text"
        )

        return Completion(
            text=text,
            model=response.model,
            usage=Usage(
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
            ),
            finish_reason=response.stop_reason or "stop",
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
        client = self._get_client()
        request = self._build_request(
            messages,
            feature=feature,
            max_tokens=max_tokens,
            json_schema=json_schema,
        )

        try:
            with client.messages.stream(**request) as stream:
                yield from stream.text_stream
        except Exception as exc:
            raise ProviderError(f"Anthropic stream failed: {exc}") from exc

    def embed(self, texts: list[str]) -> list[list[float]]:
        # Anthropic has no embeddings endpoint. Rather than silently returning
        # something useless, say so - AI_EMBEDDING_PROVIDER exists precisely so
        # generation and embedding can come from different vendors.
        raise ProviderError(
            "Anthropic does not provide an embeddings endpoint. "
            "Set AI_EMBEDDING_PROVIDER to 'mock', 'gemini', or 'ollama'."
        )
