"""A content-addressed cache for model responses.

Identical prompts are common in this application - open the same file and ask
"explain this" twice, re-run a review after an unrelated edit, replay a demo -
and every repeat is a paid round trip that returns the same answer. Keying on a
hash of everything that affects the output makes those repeats free.

The store is in-process. That is the honest limitation: run two API workers and
each keeps its own copy, so the hit rate drops and nothing is shared. The
interface is deliberately narrow (``get``/``set``/``stats``) so a Redis-backed
implementation is a drop-in replacement when the app grows past one process.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from app.core.config import AI_CACHE_MAX_ENTRIES, AI_CACHE_TTL_SECONDS
from app.services.ai.base import Completion, Message


def cache_key(
    *,
    provider: str,
    model: str,
    messages: list[Message],
    temperature: float,
    max_tokens: int,
    json_schema: dict | None,
) -> str:
    """Hash every input that can change the response.

    Leaving any of these out would serve a stale answer after a parameter
    change - a cache that is wrong is worse than no cache at all.
    """
    payload = json.dumps(
        {
            "provider": provider,
            "model": model,
            "messages": [m.as_dict() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "schema": json_schema,
        },
        sort_keys=True,
    )

    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses

        return self.hits / total if total else 0.0


class PromptCache:
    """A bounded, TTL-expiring LRU cache of completions."""

    def __init__(
        self,
        max_entries: int = AI_CACHE_MAX_ENTRIES,
        ttl_seconds: int = AI_CACHE_TTL_SECONDS,
    ) -> None:
        self._entries: OrderedDict[str, tuple[float, Completion]] = OrderedDict()
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        # FastAPI serves sync endpoints from a thread pool, so two requests can
        # touch the cache at once. OrderedDict mutation is not atomic.
        self._lock = threading.Lock()
        self.stats = CacheStats()

    def get(self, key: str) -> Completion | None:
        with self._lock:
            entry = self._entries.get(key)

            if entry is None:
                self.stats.misses += 1

                return None

            stored_at, completion = entry

            if time.time() - stored_at > self._ttl:
                del self._entries[key]
                self.stats.misses += 1

                return None

            self._entries.move_to_end(key)
            self.stats.hits += 1

            # Flagged so the caller can record a zero-cost usage row rather
            # than double-counting the tokens of the original call.
            return Completion(
                text=completion.text,
                model=completion.model,
                usage=completion.usage,
                finish_reason=completion.finish_reason,
                cached=True,
            )

    def set(self, key: str, completion: Completion) -> None:
        with self._lock:
            self._entries[key] = (time.time(), completion)
            self._entries.move_to_end(key)

            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self.stats = CacheStats()


prompt_cache = PromptCache()
