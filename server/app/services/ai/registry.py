"""Provider selection, and the one place the rest of the app talks to a model.

Two providers are resolved independently. ``AI_PROVIDER`` picks the model that
writes text; ``AI_EMBEDDING_PROVIDER`` picks the one that produces vectors.
They are separate because the best generation model is frequently not from a
vendor that sells embeddings at all - Anthropic being the obvious case.

Callers go through ``generate`` rather than touching a provider directly, so
caching and usage accounting cannot be forgotten at a call site.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.core.config import AI_EMBEDDING_PROVIDER, AI_PROVIDER
from app.services.ai.anthropic_provider import AnthropicProvider
from app.services.ai.base import (
    Completion,
    Feature,
    LLMProvider,
    Message,
    ProviderError,
)
from app.services.ai.cache import cache_key, prompt_cache
from app.services.ai.gemini import GeminiProvider
from app.services.ai.mock import MockProvider
from app.services.ai.ollama import OllamaProvider

logger = logging.getLogger(__name__)

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "mock": MockProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
}

# Instances are reused so providers can hold a client and a connection pool.
_instances: dict[str, LLMProvider] = {}


def get_provider(name: str | None = None) -> LLMProvider:
    """Return a provider by name, defaulting to the configured one."""
    key = (name or AI_PROVIDER).lower()

    if key not in _PROVIDERS:
        raise ProviderError(
            f"Unknown AI provider '{key}'. "
            f"Choose one of: {', '.join(sorted(_PROVIDERS))}."
        )

    if key not in _instances:
        _instances[key] = _PROVIDERS[key]()

    return _instances[key]


def get_embedding_provider() -> LLMProvider:
    return get_provider(AI_EMBEDDING_PROVIDER)


def describe_providers() -> list[dict]:
    """What ``GET /ai/providers`` reports.

    ``is_configured`` is computed per provider rather than assumed, so the
    response answers "what can I actually switch to right now" instead of
    listing names that would fail on first use.
    """
    described = []

    for name in sorted(_PROVIDERS):
        provider = get_provider(name)

        described.append(
            {
                "name": name,
                "model": provider.model,
                "configured": provider.is_configured,
                "active": name == AI_PROVIDER.lower(),
                "embedding_active": name == AI_EMBEDDING_PROVIDER.lower(),
                "embedding_dimensions": provider.embedding_dimensions,
                "price_per_mtok": {
                    "prompt": provider.pricing[0],
                    "completion": provider.pricing[1],
                },
            }
        )

    return described


@dataclass
class GenerationResult:
    """A completion plus everything needed to bill and audit it."""

    completion: Completion
    provider: str
    feature: Feature
    latency_ms: int
    cost_usd: float

    @property
    def text(self) -> str:
        return self.completion.text

    @property
    def cached(self) -> bool:
        return self.completion.cached


def generate(
    messages: list[Message],
    *,
    feature: Feature = "chat",
    temperature: float = 0.2,
    max_tokens: int = 1024,
    json_schema: dict | None = None,
    use_cache: bool = True,
) -> GenerationResult:
    """Run a completion through the cache and return it with its cost."""
    provider = get_provider()

    if not provider.is_configured:
        raise ProviderError(
            f"Provider '{provider.name}' is not configured. "
            "Set its API key, or set AI_PROVIDER=mock to run without one."
        )

    key = cache_key(
        provider=provider.name,
        model=provider.model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        json_schema=json_schema,
    )

    started = time.perf_counter()

    if use_cache:
        hit = prompt_cache.get(key)

        if hit is not None:
            return GenerationResult(
                completion=hit,
                provider=provider.name,
                feature=feature,
                latency_ms=int((time.perf_counter() - started) * 1000),
                # A cache hit costs nothing. Charging it again would make the
                # dashboard report savings that did not happen.
                cost_usd=0.0,
            )

    completion = provider.complete(
        messages,
        feature=feature,
        temperature=temperature,
        max_tokens=max_tokens,
        json_schema=json_schema,
    )

    if use_cache:
        prompt_cache.set(key, completion)

    return GenerationResult(
        completion=completion,
        provider=provider.name,
        feature=feature,
        latency_ms=int((time.perf_counter() - started) * 1000),
        cost_usd=provider.estimate_cost(completion.usage),
    )
