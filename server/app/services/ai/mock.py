"""A provider that needs no API key, no network, and no money.

This is the default, and it is not a stub that returns ``"lorem ipsum"``. It
produces responses in the exact shape each feature expects - valid JSON for
review and fix, prose for chat and explain - so the whole application can be
run, demoed, and tested end to end before anyone signs up for an API key.

The embeddings are real in the sense that they carry signal: a hashed n-gram
vector, the same trick ``sklearn``'s ``HashingVectorizer`` uses. Two texts that
share vocabulary land near each other, which is enough to exercise and measure
the retrieval pipeline. It is lexical similarity, not semantic - "car" and
"automobile" stay far apart. Switch to a real embedding provider before
claiming otherwise.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterator

from app.services.ai.base import (
    Completion,
    Feature,
    LLMProvider,
    Message,
    Usage,
    estimate_tokens,
)

_WORD = re.compile(r"[a-z_][a-z0-9_]{1,}")


def _tokenize(text: str) -> list[str]:
    """Words plus character 4-grams.

    Words alone are brittle across naming styles; character n-grams let
    ``get_user`` and ``getUserById`` share signal.
    """
    lowered = text.lower()
    tokens = _WORD.findall(lowered)

    squashed = re.sub(r"[^a-z0-9]+", " ", lowered)
    tokens.extend(squashed[i : i + 4] for i in range(0, max(0, len(squashed) - 3)))

    return tokens


def _bucket(token: str, dimensions: int) -> tuple[int, float]:
    """Map a token to a vector slot and a sign.

    The sign comes from an independent bit of the same hash. Without it,
    unrelated tokens colliding in a bucket only ever reinforce each other;
    with it, collisions cancel on average and the noise floor stays low.
    """
    digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
    value = int.from_bytes(digest, "big")

    return value % dimensions, 1.0 if (value >> 63) & 1 else -1.0


class MockProvider(LLMProvider):
    name = "mock"
    pricing = (0.0, 0.0)
    embedding_dimensions = 256

    @property
    def is_configured(self) -> bool:
        return True

    @property
    def model(self) -> str:
        return "mock-1"

    def complete(
        self,
        messages: list[Message],
        *,
        feature: Feature = "chat",
        temperature: float = 0.2,
        max_tokens: int = 1024,
        json_schema: dict | None = None,
    ) -> Completion:
        prompt = "\n".join(m.content for m in messages)
        text = self._respond(feature, messages)

        return Completion(
            text=text,
            model=self.model,
            usage=Usage(
                prompt_tokens=estimate_tokens(prompt),
                completion_tokens=estimate_tokens(text),
            ),
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
        text = self._respond(feature, messages)

        # Chunked by word so the client's streaming path gets a realistic
        # sequence of deltas rather than one giant frame.
        for word in text.split(" "):
            yield word + " "

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []

        for text in texts:
            vector = [0.0] * self.embedding_dimensions

            for token in _tokenize(text):
                index, sign = _bucket(token, self.embedding_dimensions)
                vector[index] += sign

            norm = math.sqrt(sum(value * value for value in vector))

            # An empty or whitespace-only chunk has no direction. Leaving it as
            # zeros keeps cosine similarity at 0 against everything, which is
            # the honest answer - dividing by zero would not be.
            if norm > 0:
                vector = [value / norm for value in vector]

            vectors.append(vector)

        return vectors

    def _respond(self, feature: Feature, messages: list[Message]) -> str:
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"),
            "",
        )

        if feature == "review":
            return json.dumps(
                {
                    "findings": [
                        {
                            "path": "example.py",
                            "line": 1,
                            "severity": "info",
                            "message": (
                                "Mock provider active - no real review was "
                                "performed. Set AI_PROVIDER to a configured "
                                "provider for genuine findings."
                            ),
                            "suggestion": None,
                        }
                    ]
                }
            )

        if feature == "fix":
            return json.dumps(
                {
                    "summary": (
                        "Mock provider active - returning the files unchanged."
                    ),
                    "changes": [],
                }
            )

        if feature == "explain":
            return (
                "This code was not analysed by a real model: the mock provider "
                "is active. It received "
                f"{len(last_user.splitlines())} lines of context and would "
                "normally return a walkthrough of the control flow, the "
                "inputs and outputs, and anything surprising. Set AI_PROVIDER "
                "to anthropic, gemini, or ollama for a real explanation."
            )

        return (
            "Mock provider active, so this reply is generated locally and "
            "costs nothing. Your message was "
            f"{estimate_tokens(last_user)} tokens. Every other part of the "
            "pipeline - retrieval, streaming, token accounting, caching - ran "
            "for real. Set AI_PROVIDER to use a live model."
        )
