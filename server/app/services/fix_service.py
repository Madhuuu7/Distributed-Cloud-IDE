"""The agentic fix loop: propose a patch, run the tests, read the failure, retry.

This is the part that makes the assistant more than a chat window. A model
asked to fix code produces a plausible-looking patch; whether it *works* is a
separate question, and the only honest way to answer it is to run the tests.
So the loop closes: generate, execute in the sandbox, feed the real failure
output back, and try again.

Three constraints shape the design.

**It never writes to project files.** A run ends holding a proposed patch and a
human calls ``/apply``. An agent that edits a shared workspace unattended is a
feature people switch off after the first bad day.

**Iterations are hard-capped.** A model that misreads a failure will happily
produce the same wrong patch forever, and each attempt costs tokens.

**The tests run in the same locked-down container as everything else** - no
network, read-only root, memory and CPU ceilings. The code being tested was
written by a language model, which is exactly the code you would want
sandboxed.
"""

from __future__ import annotations

import difflib
import json
import logging
import shlex
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import AI_MAX_TOKENS, FIX_ITERATION_CEILING
from app.models.ai import AIUsage
from app.models.file import FileNode
from app.models.fix import FixIteration, FixRun
from app.services.ai import Message, ProviderError, generate
from app.services.ai.prompts import FIX_SCHEMA, FIX_SYSTEM
from app.services.execution_service import (
    ExecutionError,
    ExecutionResult,
    default_test_command,
    run_project,
)

logger = logging.getLogger(__name__)


def project_files(db: Session, project_id: int) -> dict[str, str]:
    return {
        node.name: node.content
        for node in db.query(FileNode).filter(FileNode.project_id == project_id)
    }


def dominant_language(db: Session, project_id: int) -> str:
    """The language most of the project is written in.

    A project is one runtime for our purposes, so the majority wins rather than
    trying to run a mixed-language test suite.
    """
    counts = Counter(
        node.language
        for node in db.query(FileNode).filter(FileNode.project_id == project_id)
        if node.language in ("python", "javascript")
    )

    if not counts:
        return "python"

    return counts.most_common(1)[0][0]


def render_files(files: dict[str, str]) -> str:
    return "\n\n".join(
        f"=== {name} ===\n{content}" for name, content in sorted(files.items())
    )


def describe_failure(result: ExecutionResult) -> str:
    parts = [f"Exit code: {result.exit_code}"]

    if result.timed_out:
        parts.append("The test command timed out and was killed.")

    if result.stdout.strip():
        parts.append(f"stdout:\n{result.stdout}")

    if result.stderr.strip():
        parts.append(f"stderr:\n{result.stderr}")

    return "\n\n".join(parts)


def compute_diff(before: dict[str, str], after: dict[str, str]) -> str:
    """A unified diff of the proposed change, for display only.

    The model returns whole files - it is far more reliable at that than at
    emitting a well-formed diff - so the diff is derived here, where it cannot
    be malformed.
    """
    blocks: list[str] = []

    for path in sorted(after):
        original = before.get(path, "")

        if original == after[path]:
            continue

        blocks.append(
            "\n".join(
                difflib.unified_diff(
                    original.splitlines(),
                    after[path].splitlines(),
                    fromfile=f"a/{path}" if path in before else "/dev/null",
                    tofile=f"b/{path}",
                    lineterm="",
                )
            )
        )

    return "\n".join(blocks)


def _finish(
    db: Session, run: FixRun, status: str, *, summary: str = None, error: str = None
) -> FixRun:
    run.status = status

    if summary is not None:
        run.summary = summary

    if error is not None:
        run.error = error

    db.commit()
    db.refresh(run)

    return run


def execute_fix_run(db: Session, run_id: int) -> FixRun:
    """Drive one fix run to completion.

    Runs synchronously on whatever thread calls it; the API hands it to a
    background task so the request can return ``202`` immediately.
    """
    run = db.get(FixRun, run_id)

    if run is None:
        raise ValueError(f"No fix run with id {run_id}")

    if run.status == "cancelled":
        return run

    run.status = "running"
    db.commit()

    original = project_files(db, run.project_id)

    if not original:
        return _finish(db, run, "failed", error="The project has no files.")

    language = dominant_language(db, run.project_id)
    command = (
        shlex.split(run.test_command)
        if run.test_command
        else default_test_command(language)
    )

    try:
        # Iteration 0 is the baseline. Without it there is no way to tell a fix
        # that worked from a suite that was already green, and reporting the
        # latter as a success would be a lie the dashboard repeats forever.
        baseline = run_project(language, original, command)
    except ExecutionError as exc:
        return _finish(db, run, "failed", error=str(exc))

    db.add(
        FixIteration(
            fix_run_id=run.id,
            iteration=0,
            reasoning="Baseline run before any changes.",
            stdout=baseline.stdout,
            stderr=baseline.stderr,
            exit_code=baseline.exit_code,
            passed=baseline.exit_code == 0,
        )
    )
    db.commit()

    if baseline.exit_code == 0:
        return _finish(
            db,
            run,
            "succeeded",
            summary="The tests already passed; no changes were needed.",
        )

    max_iterations = min(run.max_iterations, FIX_ITERATION_CEILING)
    failure = describe_failure(baseline)
    attempts: list[str] = []

    for iteration in range(1, max_iterations + 1):
        if db.get(FixRun, run.id).status == "cancelled":
            return _finish(db, run, "cancelled")

        prompt = _build_prompt(run, original, failure, attempts)

        try:
            result = generate(
                [Message("system", FIX_SYSTEM), Message("user", prompt)],
                feature="fix",
                max_tokens=AI_MAX_TOKENS,
                json_schema=FIX_SCHEMA,
                # Caching is off here on purpose. A cached response would
                # replay the patch that already failed, turning the loop into
                # the same wrong answer repeated until the budget runs out.
                use_cache=False,
            )
        except ProviderError as exc:
            return _finish(db, run, "failed", error=str(exc))

        db.add(
            AIUsage(
                user_id=run.user_id,
                feature="fix",
                provider=result.provider,
                model=result.completion.model,
                prompt_tokens=result.completion.usage.prompt_tokens,
                completion_tokens=result.completion.usage.completion_tokens,
                cost_usd=result.cost_usd,
                latency_ms=result.latency_ms,
                cached=result.cached,
            )
        )
        db.commit()

        patch = _parse_patch(result.text)

        if patch is None:
            attempts.append(
                f"Attempt {iteration} returned output that was not a valid patch."
            )

            db.add(
                FixIteration(
                    fix_run_id=run.id,
                    iteration=iteration,
                    reasoning="Model output could not be parsed as a patch.",
                    passed=False,
                )
            )
            db.commit()

            continue

        candidate = dict(original)

        for change in patch["changes"]:
            candidate[change["path"]] = change["content"]

        if candidate == original:
            attempts.append(f"Attempt {iteration} proposed no actual change.")

            db.add(
                FixIteration(
                    fix_run_id=run.id,
                    iteration=iteration,
                    patch=json.dumps(patch),
                    reasoning=patch.get("reasoning"),
                    passed=False,
                )
            )
            db.commit()

            continue

        try:
            outcome = run_project(language, candidate, command)
        except ExecutionError as exc:
            return _finish(db, run, "failed", error=str(exc))

        db.add(
            FixIteration(
                fix_run_id=run.id,
                iteration=iteration,
                patch=json.dumps(patch),
                reasoning=patch.get("reasoning"),
                stdout=outcome.stdout,
                stderr=outcome.stderr,
                exit_code=outcome.exit_code,
                passed=outcome.exit_code == 0,
            )
        )
        db.commit()

        if outcome.exit_code == 0:
            run.proposed_patch = json.dumps(patch)

            return _finish(
                db,
                run,
                "awaiting_approval",
                summary=patch.get("summary") or "Tests pass with this patch.",
            )

        failure = describe_failure(outcome)
        attempts.append(
            f"Attempt {iteration}: {patch.get('summary', 'no summary')} "
            f"- still failing."
        )

    return _finish(
        db,
        run,
        "failed",
        error=f"Gave up after {max_iterations} attempts; the tests still fail.",
    )


def _build_prompt(
    run: FixRun,
    files: dict[str, str],
    failure: str,
    attempts: list[str],
) -> str:
    sections = [
        f"Task: {run.instruction}",
        f"Current project files:\n\n{render_files(files)}",
        f"The test command failed:\n\n{failure}",
    ]

    if attempts:
        # Previous attempts are listed so the model does not repeat one. The
        # failing patches themselves are left out - they crowd the context and
        # tend to anchor the model to the approach that already did not work.
        sections.append(
            "Approaches already tried and rejected:\n"
            + "\n".join(f"- {attempt}" for attempt in attempts)
        )

    return "\n\n".join(sections)


def _parse_patch(text: str) -> dict | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict) or not isinstance(
        payload.get("changes"), list
    ):
        return None

    changes = []

    for change in payload["changes"]:
        if (
            isinstance(change, dict)
            and isinstance(change.get("path"), str)
            and isinstance(change.get("content"), str)
        ):
            changes.append(change)

    payload["changes"] = changes

    return payload


def apply_patch(db: Session, run: FixRun) -> list[str]:
    """Write an approved patch to the project's files.

    Returns the paths that changed. Creating a file the patch names but the
    project does not have is intentional - a fix that requires a new test
    helper should not fail because the file did not exist yet.
    """
    patch = json.loads(run.proposed_patch)
    touched = []

    for change in patch["changes"]:
        node = (
            db.query(FileNode)
            .filter(
                FileNode.project_id == run.project_id,
                FileNode.name == change["path"],
            )
            .first()
        )

        if node is None:
            from app.services.languages import detect_language

            node = FileNode(
                project_id=run.project_id,
                name=change["path"],
                path=f"/{change['path']}",
                content=change["content"],
                language=detect_language(change["path"]),
            )
            db.add(node)
        else:
            node.content = change["content"]

        touched.append(change["path"])

    run.status = "succeeded"
    run.updated_at = datetime.now(timezone.utc)
    db.commit()

    return touched
