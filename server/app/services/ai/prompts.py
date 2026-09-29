"""System prompts and context packing.

Prompts live here rather than inline in the routers for the same reason SQL
does not live in a view: they are the part most likely to change, most worth
reviewing on its own, and most useful to diff when output quality moves.

``pack_context`` enforces a character budget. Without one, indexing a large
project eventually produces a request that either costs far more than intended
or is rejected outright, and the failure arrives at the worst moment - when the
project is big enough to be interesting.
"""

from __future__ import annotations

from app.services.rag.search import SearchHit

# Roughly four characters per token, so this is about 6k tokens of code
# context. Large enough for six or seven functions, small enough that a chat
# turn stays cheap.
MAX_CONTEXT_CHARS = 24_000

CHAT_SYSTEM = """You are an AI teammate embedded in a collaborative code editor.

You are given excerpts from the team's actual codebase. Ground every claim in \
them and cite the file and line range you used, like `auth.py:27-55`.

If the excerpts do not contain the answer, say so plainly and name what you \
would need to see. Do not invent files, functions, or behaviour that is not in \
the provided code - a confident wrong answer about someone's codebase costs \
more than an honest "not in the code I was shown"."""

EXPLAIN_SYSTEM = """You explain code to a competent developer who has not read \
this particular file.

Cover what it does, how the control flow moves, what the inputs and outputs \
are, and anything genuinely surprising. Skip the line-by-line narration of \
obvious statements. Be specific about edge cases the code handles or misses."""

REVIEW_SYSTEM = """You are reviewing a diff the way a thorough senior engineer \
would.

Report only defects you can point at: bugs, security holes, missing error \
handling, race conditions, resource leaks, and misleading names. Every finding \
must name a real line in the code you were given.

Do not report style preferences, do not restate what the code does, and do not \
pad the list - an empty findings array is the correct answer for clean code, \
and reviewers who always find something get ignored."""

FIX_SYSTEM = """You are fixing code so that a test command passes.

You will be given the current files, the instruction, and - after the first \
attempt - the exact output of the failing test. Read the failure before \
changing anything: the error message usually names the problem.

Return the complete new content of every file you change. Do not return a \
diff, do not abbreviate with comments like "... rest unchanged", and do not \
touch files you have no reason to change.

If the test failure shows your previous attempt was wrong, say what you \
misread and take a different approach rather than making the same edit again."""


# Structured output schemas. These are the contract between the model and the
# code that parses it, which is why they are strict: `additionalProperties`
# false means a hallucinated extra key is a validation error rather than
# something silently ignored.
REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "line": {"type": "integer"},
                    "severity": {
                        "type": "string",
                        "enum": ["info", "minor", "major", "critical"],
                    },
                    "message": {"type": "string"},
                    "suggestion": {"type": ["string", "null"]},
                },
                "required": ["path", "line", "severity", "message", "suggestion"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}

FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "reasoning": {"type": "string"},
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "reasoning", "changes"],
    "additionalProperties": False,
}


def pack_context(hits: list[SearchHit], budget: int = MAX_CONTEXT_CHARS) -> str:
    """Render retrieved chunks into a prompt, highest-scoring first.

    Packing in rank order and stopping at the budget means the best evidence is
    always included. Truncating the concatenated string instead would cut the
    lowest-ranked chunk in half and leave the model reading a fragment.
    """
    if not hits:
        return ""

    blocks: list[str] = []
    used = 0

    for hit in hits:
        block = (
            f"--- {hit.chunk.path}:{hit.chunk.start_line}-{hit.chunk.end_line}"
            + (f" ({hit.chunk.symbol})" if hit.chunk.symbol else "")
            + f"\n{hit.chunk.text}\n"
        )

        if used + len(block) > budget:
            break

        blocks.append(block)
        used += len(block)

    return "\n".join(blocks)


def build_chat_prompt(question: str, context: str) -> str:
    if not context:
        return (
            f"{question}\n\n"
            "(No codebase excerpts were retrieved for this question. Answer "
            "from general knowledge and say that you had no project context.)"
        )

    return (
        f"Here are the most relevant excerpts from the codebase:\n\n"
        f"{context}\n\n"
        f"Question: {question}"
    )
