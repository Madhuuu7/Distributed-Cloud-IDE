"""Hybrid retrieval: keyword scoring and vector similarity, blended.

Neither ranker is sufficient on its own, and the failures are complementary.
Ask "where do we check the JWT signature" and a vector search finds the auth
module even though the file never says "JWT signature"; ask for
``ACCESS_TOKEN_EXPIRE_MINUTES`` and only keyword matching reliably returns the
one line that defines it. Blending them covers both.

Both component scores are returned alongside the blended one, so a bad result
can be diagnosed - "the vector score was high and the keyword score was zero"
is actionable in a way that a single opaque number is not.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from app.core.config import RAG_KEYWORD_WEIGHT, RAG_TOP_K, RAG_VECTOR_WEIGHT
from app.models.rag import CodeChunk
from app.services.ai import get_embedding_provider
from app.services.rag.index import unpack_vector

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass
class SearchHit:
    chunk: CodeChunk
    score: float
    keyword_score: float
    vector_score: float


def tokenize(text: str) -> list[str]:
    """Split into identifiers, then also into their camelCase/snake_case parts.

    Without splitting, a query for "user" misses ``get_user_by_id`` entirely -
    the whole identifier is one token and never matches.
    """
    tokens: list[str] = []

    for word in _TOKEN.findall(text.lower()):
        tokens.append(word)
        tokens.extend(part for part in word.split("_") if len(part) > 1)

    for word in _TOKEN.findall(text):
        parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", word)

        if len(parts) > 1:
            tokens.extend(part.lower() for part in parts if len(part) > 1)

    return tokens


def _keyword_scores(query: str, chunks: list[CodeChunk]) -> np.ndarray:
    """TF-IDF-weighted overlap between the query and each chunk.

    IDF matters here more than in prose: tokens like ``self``, ``return``, and
    ``import`` appear in nearly every chunk of a Python project, and without
    down-weighting them a query containing one would rank essentially at
    random.
    """
    query_tokens = set(tokenize(query))

    if not query_tokens or not chunks:
        return np.zeros(len(chunks), dtype=np.float64)

    chunk_tokens = [Counter(tokenize(chunk.text)) for chunk in chunks]

    document_frequency = Counter()

    for counts in chunk_tokens:
        for token in query_tokens:
            if token in counts:
                document_frequency[token] += 1

    total = len(chunks)
    scores = np.zeros(total, dtype=np.float64)

    for index, counts in enumerate(chunk_tokens):
        score = 0.0

        for token in query_tokens:
            occurrences = counts.get(token, 0)

            if not occurrences:
                continue

            idf = math.log(1 + total / (1 + document_frequency[token]))
            # Sub-linear in term frequency: a chunk mentioning a token twenty
            # times is not twenty times more relevant than one mentioning it
            # once, and without the damping long files always win.
            score += (1 + math.log(occurrences)) * idf

        scores[index] = score

    return scores


def _normalise(values: np.ndarray) -> np.ndarray:
    """Scale to [0, 1] so two differently-scaled rankers can be blended.

    Raw cosine similarity sits in [-1, 1] and the keyword score is unbounded
    above; adding them directly would let whichever happens to have the larger
    range dominate the blend.
    """
    if values.size == 0:
        return values

    smallest = float(values.min())
    largest = float(values.max())

    if largest - smallest < 1e-12:
        # Every candidate scored the same, so this ranker has no opinion.
        # Returning zeros lets the other ranker decide, rather than manufacturing
        # an arbitrary ordering.
        return np.zeros_like(values)

    return (values - smallest) / (largest - smallest)


def search(
    db: Session,
    *,
    project_id: int,
    query: str,
    k: int = RAG_TOP_K,
) -> list[SearchHit]:
    chunks = db.query(CodeChunk).filter(CodeChunk.project_id == project_id).all()

    if not chunks:
        return []

    keyword_raw = _keyword_scores(query, chunks)

    provider = get_embedding_provider()
    vector_raw = np.zeros(len(chunks), dtype=np.float64)

    # Vectors built by a different model are not comparable to a query embedded
    # by the current one. Rather than return confidently wrong rankings, drop
    # to keyword-only and let the caller see vector_score == 0.
    usable = [
        index
        for index, chunk in enumerate(chunks)
        if chunk.embedding_model == provider.model
    ]

    if usable and provider.is_configured:
        query_vector = np.asarray(provider.embed([query])[0], dtype=np.float64)
        norm = np.linalg.norm(query_vector)

        if norm > 0:
            query_vector = query_vector / norm

            matrix = np.vstack(
                [unpack_vector(chunks[index].embedding) for index in usable]
            ).astype(np.float64)

            lengths = np.linalg.norm(matrix, axis=1)
            lengths[lengths == 0] = 1.0

            vector_raw[usable] = (matrix @ query_vector) / lengths

    keyword = _normalise(keyword_raw)
    vector = _normalise(vector_raw)
    blended = RAG_KEYWORD_WEIGHT * keyword + RAG_VECTOR_WEIGHT * vector

    ranked = sorted(
        (
            SearchHit(
                chunk=chunks[index],
                score=float(blended[index]),
                keyword_score=float(keyword[index]),
                vector_score=float(vector[index]),
            )
            for index in range(len(chunks))
        ),
        key=lambda hit: hit.score,
        reverse=True,
    )

    # A chunk that matched on neither ranker is noise. Padding the results up
    # to k with zero-scoring chunks would only dilute the prompt context.
    return [hit for hit in ranked[:k] if hit.score > 0]
