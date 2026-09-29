"""Split source files into retrievable units.

The naive approach - cut every 40 lines - is what makes RAG over code feel
broken. A fixed window routinely starts halfway through one function and ends
halfway through the next, so a retrieved chunk shows a body with no signature
and the model has to guess what it was looking at.

This splits on declaration boundaries instead, so a chunk is a whole function
or class and carries its own name. Retrieval quality improves for a reason that
is easy to state in an interview: the unit of retrieval now matches the unit of
meaning.

It is regex-based rather than a real parser. That is a deliberate trade - no
build step, no native dependency, and it degrades to line windows on anything
it does not recognise instead of failing. A malformed file produces slightly
worse chunks, never an exception.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import RAG_CHUNK_OVERLAP_LINES, RAG_MAX_CHUNK_LINES


@dataclass(frozen=True)
class Chunk:
    path: str
    language: str
    start_line: int  # 1-indexed, inclusive
    end_line: int  # 1-indexed, inclusive
    symbol: str | None
    text: str

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1

    def as_context(self) -> str:
        """Render for a prompt, with the location the model needs to cite it."""
        header = f"# {self.path}:{self.start_line}-{self.end_line}"

        if self.symbol:
            header += f" ({self.symbol})"

        return f"{header}\n{self.text}"


# A declaration is only a boundary at the start of a line (modulo indentation),
# which keeps the word "class" inside a string or comment from splitting a file.
_DECLARATION_PATTERNS: dict[str, re.Pattern[str]] = {
    "python": re.compile(
        r"^(?P<indent>[ \t]*)(?:async\s+)?(?:def|class)\s+(?P<name>\w+)"
    ),
    "javascript": re.compile(
        r"^(?P<indent>[ \t]*)(?:export\s+)?(?:async\s+)?"
        r"(?:function\s+(?P<name>\w+)"
        r"|class\s+(?P<name2>\w+)"
        r"|(?:const|let|var)\s+(?P<name3>\w+)\s*=\s*(?:async\s*)?(?:\(|function))"
    ),
}

_DECLARATION_PATTERNS["typescript"] = _DECLARATION_PATTERNS["javascript"]


def _symbol_from(match: re.Match[str]) -> str | None:
    for group in ("name", "name2", "name3"):
        try:
            value = match.group(group)
        except IndexError:
            continue

        if value:
            return value

    return None


def chunk_file(path: str, content: str, language: str) -> list[Chunk]:
    """Split one file into chunks."""
    lines = content.splitlines()

    if not lines:
        return []

    pattern = _DECLARATION_PATTERNS.get(language)

    if pattern is None:
        return _window_chunks(path, language, lines, start_offset=0, symbol=None)

    # Collect every declaration boundary, then cut between consecutive ones.
    boundaries: list[tuple[int, str | None]] = []

    for index, line in enumerate(lines):
        match = pattern.match(line)

        if match:
            boundaries.append((index, _symbol_from(match)))

    if not boundaries:
        return _window_chunks(path, language, lines, start_offset=0, symbol=None)

    chunks: list[Chunk] = []

    # Imports and module-level constants sit above the first declaration and
    # are frequently what a question is actually about ("what does this file
    # import?"), so the preamble becomes its own chunk rather than being lost.
    first_boundary = boundaries[0][0]

    if first_boundary > 0:
        chunks.extend(
            _window_chunks(
                path,
                language,
                lines[:first_boundary],
                start_offset=0,
                symbol="module preamble",
            )
        )

    # A declaration immediately followed by a nested one - a class header above
    # its first method - has no body of its own. Emitted alone it becomes a
    # one-line chunk that matches the class name and then tells the reader
    # nothing. It is carried forward as a prefix on the next chunk instead, so
    # the method arrives with the class it belongs to.
    pending_prefix: list[str] = []

    for position, (line_index, symbol) in enumerate(boundaries):
        end_index = (
            boundaries[position + 1][0]
            if position + 1 < len(boundaries)
            else len(lines)
        )
        body = lines[line_index:end_index]

        if pending_prefix:
            body = pending_prefix + body
            line_index -= len(pending_prefix)
            pending_prefix = []

        has_body = any(line.strip() for line in body[1:])

        if not has_body and position + 1 < len(boundaries):
            pending_prefix = body

            continue

        # A declaration longer than the cap - a large class, a god function -
        # is still windowed, but every window keeps the symbol name so it stays
        # attributable.
        if len(body) > RAG_MAX_CHUNK_LINES:
            chunks.extend(
                _window_chunks(
                    path,
                    language,
                    body,
                    start_offset=line_index,
                    symbol=symbol,
                )
            )

            continue

        text = "\n".join(body).strip()

        if not text:
            continue

        chunks.append(
            Chunk(
                path=path,
                language=language,
                start_line=line_index + 1,
                end_line=end_index,
                symbol=symbol,
                text=text,
            )
        )

    return chunks


def _window_chunks(
    path: str,
    language: str,
    lines: list[str],
    *,
    start_offset: int,
    symbol: str | None,
) -> list[Chunk]:
    """Fixed windows with overlap, for content with no usable structure.

    The overlap exists so a fact that straddles a cut survives in at least one
    window intact.
    """
    if not lines:
        return []

    step = max(1, RAG_MAX_CHUNK_LINES - RAG_CHUNK_OVERLAP_LINES)
    chunks: list[Chunk] = []

    for start in range(0, len(lines), step):
        window = lines[start : start + RAG_MAX_CHUNK_LINES]
        text = "\n".join(window).strip()

        if not text:
            continue

        chunks.append(
            Chunk(
                path=path,
                language=language,
                start_line=start_offset + start + 1,
                end_line=start_offset + start + len(window),
                symbol=symbol,
                text=text,
            )
        )

        # The final window already reached the end; another pass would only
        # re-emit its tail.
        if start + RAG_MAX_CHUNK_LINES >= len(lines):
            break

    return chunks
