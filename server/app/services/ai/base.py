"""The provider interface every LLM backend implements.

The application never imports a vendor SDK directly. It asks the registry for
an ``LLMProvider`` and calls this interface, so swapping Anthropic for a local
Ollama model is a change to one environment variable rather than a change to
any calling code.

``complete`` returns a structured ``Completion`` rather than a bare string
because token counts and latency have to be recorded for every call - that
accounting is what ``GET /ai/usage`` reports on.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["system", "user", "assistant"]

# Every AI-backed endpoint tags its calls so usage can be split by feature.
Feature = Literal["chat", "explain", "review", "fix", "embedding", "search"]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    usage: Usage = field(default_factory=Usage)
    finish_reason: str = "stop"
    # Set by the caching layer, not by the provider itself.
    cached: bool = False


class ProviderError(RuntimeError):
    """The provider could not be reached or is not configured.

    Surfaced to clients as a 503 - it is an upstream failure, not the caller's
    fault, and retrying later is reasonable.
    """


def estimate_tokens(text: str) -> int:
    """Approximate a token count for providers that do not report one.

    Four characters per token is the usual rule of thumb for English and for
    code. It is only ever used for providers that return no usage data (today,
    Ollama), and it is marked as an estimate in the usage table so nobody reads
    those rows as exact.
    """
    return max(1, len(text) // 4)


class LLMProvider(ABC):
    """A text-generation and embedding backend."""

    #: Stable identifier used in config, usage rows, and ``GET /ai/providers``.
    name: str = "base"

    #: Price per one million tokens, in USD, as ``(prompt, completion)``.
    #: ``(0.0, 0.0)`` means the provider is free to call - local or mocked.
    pricing: tuple[float, float] = (0.0, 0.0)

    #: Length of the vectors ``embed`` returns. Changing it invalidates every
    #: stored embedding, so the index records the model it was built with.
    embedding_dimensions: int = 256

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether this provider has everything it needs to serve a request."""

    @property
    @abstractmethod
    def model(self) -> str:
        """The model identifier this provider will use."""

    @abstractmethod
    def complete(
        self,
        messages: list[Message],
        *,
        feature: Feature = "chat",
        temperature: float = 0.2,
        max_tokens: int = 1024,
        json_schema: dict | None = None,
    ) -> Completion:
        """Generate a single response."""

    @abstractmethod
    def stream(
        self,
        messages: list[Message],
        *,
        feature: Feature = "chat",
        temperature: float = 0.2,
        max_tokens: int = 1024,
        json_schema: dict | None = None,
    ) -> Iterator[str]:
        """Generate a response as a sequence of text deltas."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts into vectors of length ``embedding_dimensions``."""

    def estimate_cost(self, usage: Usage) -> float:
        """Cost of a call in USD, from the provider's published per-token rates."""
        prompt_rate, completion_rate = self.pricing

        return (
            usage.prompt_tokens * prompt_rate
            + usage.completion_tokens * completion_rate
        ) / 1_000_000
