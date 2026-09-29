# AI Developer Collaboration Platform — API contract

This document is the contract. Implementation follows it, and the Postman
collection in `docs/api/postman/` asserts it. If the code and this document
disagree, one of them is a bug.

Base URL: `http://localhost:8000`. Every endpoint except `/health`,
`/auth/login`, and `/auth/signup` requires `Authorization: Bearer <token>`.

## What is being added

The existing API is single-player: a user owns projects, owns files, runs code.
This adds four capabilities on top, without breaking any existing endpoint.

| Capability | Surface |
|---|---|
| Shared workspaces with roles | `/workspaces/*` |
| An AI teammate that has read the code | `/ai/*` |
| Semantic search over a project | `/projects/{id}/index`, `/search` |
| Agentic fix loop (patch → test → retry) | `/fix-runs/*` |
| Live collaboration | `WS /ws/workspace/{id}` |

## Authorisation model

Three roles, strictly ordered:

| Role | Read files | Write files | Run code | Use AI | Manage members |
|---|---|---|---|---|---|
| `viewer` | yes | no | no | yes | no |
| `editor` | yes | yes | yes | yes | no |
| `owner` | yes | yes | yes | yes | yes |

A project is reachable if the caller owns it **or** is a member of the
workspace it belongs to. Two rules carry over from the existing API and are not
negotiable:

1. **Resources you cannot see return `404`, never `403`.** The API must not
   confirm that a resource exists to someone with no access to it.
2. **`403` is reserved for "you are in this workspace but your role is too
   low".** At that point the caller already knows the resource exists, so
   naming the real reason leaks nothing.

## Workspaces

| Method | Path | Role | Notes |
|---|---|---|---|
| `GET` | `/workspaces` | any | Workspaces the caller belongs to |
| `POST` | `/workspaces` | — | Creator becomes `owner`. `201` |
| `GET` | `/workspaces/{id}` | any | Includes the caller's own role |
| `DELETE` | `/workspaces/{id}` | owner | Detaches projects, does not delete them |
| `GET` | `/workspaces/{id}/members` | any | |
| `POST` | `/workspaces/{id}/members` | owner | Invite by email. `404` if no such user, `409` if already a member |
| `PATCH` | `/workspaces/{id}/members/{user_id}` | owner | Change role. Cannot demote the last owner (`409`) |
| `DELETE` | `/workspaces/{id}/members/{user_id}` | owner, or self | Leaving is always allowed except for the last owner |

`POST /projects` accepts an optional `workspace_id`. Passing a workspace the
caller is not an `editor`/`owner` of returns `403`.

## AI

Every AI endpoint records a usage row: provider, model, prompt tokens,
completion tokens, cost estimate, latency, cache hit. That is what makes
`/ai/usage` possible, and it is the reason the provider layer returns a
structured result rather than a bare string.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/ai/providers` | Which providers are configured and which is active |
| `POST` | `/ai/chat` | `{conversation_id?, message, project_id?, use_rag}` → full reply |
| `POST` | `/ai/chat/stream` | Same body, `text/event-stream` of `token` then `done` events |
| `GET` | `/ai/conversations` | Caller's conversations, newest first |
| `GET` | `/ai/conversations/{id}` | With messages |
| `DELETE` | `/ai/conversations/{id}` | |
| `POST` | `/ai/explain` | `{file_id, start_line?, end_line?}` → explanation of that code |
| `POST` | `/ai/review` | `{project_id, file_ids?}` → `[{path, line, severity, message, suggestion}]` |
| `GET` | `/ai/usage` | `?days=30` → daily totals, per-feature split, cache hit rate |

### Provider abstraction

`LLMProvider` is an interface with `complete()`, `stream()`, and `embed()`.
Four implementations ship: `mock`, `anthropic`, `gemini`, `ollama`. `mock` is
the default and requires no API key, so the whole application — and the whole
test suite — runs at zero cost. `AI_PROVIDER` selects one at startup.

A response is cached under `sha256(provider + model + prompt + temperature)`.
Repeated identical prompts cost nothing and return in single-digit
milliseconds; `/ai/usage` reports the hit rate.

## Retrieval

| Method | Path | Notes |
|---|---|---|
| `POST` | `/projects/{id}/index` | Chunk + embed the project. `202`, returns chunk count |
| `GET` | `/projects/{id}/index` | `{status, chunk_count, indexed_at, stale}` |
| `POST` | `/search` | `{query, project_id, k?}` → ranked chunks with scores |

Chunking is structural, not fixed-width: Python and JavaScript sources split on
function and class boundaries so a retrieved chunk is a complete unit of code.
Anything else falls back to overlapping line windows.

Ranking is hybrid. Keyword score (token overlap, IDF-weighted) and vector score
(cosine) are each normalised to `[0, 1]` and combined as
`0.3 * keyword + 0.7 * vector`. Pure vector search loses exact identifier
matches; pure keyword search loses paraphrases. The response returns both
component scores so the blend is inspectable rather than a black box.

`VectorStore` is an interface. The default implementation keeps vectors in
SQLite and scores them with NumPy, which is honest for a few thousand chunks.
A pgvector implementation slots in behind the same interface when the data
outgrows that.

## Agentic fix loop

The feature that makes this more than a chat wrapper: the AI writes a patch,
the patch runs against the existing hardened Docker sandbox, and the AI reads
the failure and tries again.

| Method | Path | Notes |
|---|---|---|
| `POST` | `/fix-runs` | `{project_id, instruction, test_command?, max_iterations?}` → `202` |
| `GET` | `/fix-runs/{id}` | Status, every iteration, the proposed diff |
| `GET` | `/fix-runs` | `?project_id=` — history |
| `POST` | `/fix-runs/{id}/apply` | Write the approved patch to the project files |
| `POST` | `/fix-runs/{id}/cancel` | |

States: `queued → running → (succeeded | failed | cancelled)`, and
`awaiting_approval` once a patch passes its tests.

**A fix run never writes to project files on its own.** It produces a diff; a
human calls `/apply`. `max_iterations` is capped server-side (default 3, hard
ceiling 10) so a confused model cannot burn tokens indefinitely.

## Realtime

`WS /ws/workspace/{id}?token=<jwt>` — the token rides in the query string
because browsers cannot set headers on a WebSocket handshake. It is validated
exactly like a bearer token, and rejected connections close with `4401`.

One socket multiplexes every channel. Messages are JSON envelopes:

| `type` | Direction | Payload |
|---|---|---|
| `presence.sync` | server → client | Everyone currently connected |
| `presence.cursor` | both | `{file_id, line, column}` |
| `doc.update` | both | `{file_id, update}` — base64 Yjs update, rebroadcast to others |
| `chat.message` | both | `{body, file_id?, line?}` — persisted |
| `ai.token` | server → client | Streamed AI reply, so the whole room sees it |
| `error` | server → client | `{code, detail}` |

Unknown `type` values are ignored rather than fatal, so a newer client can talk
to an older server.

## Error shape

Every error is `{"detail": "..."}`, matching FastAPI's default so existing
clients need no change.

| Status | Meaning |
|---|---|
| `400` | Malformed input that Pydantic did not catch |
| `401` | Missing, expired, or invalid token |
| `403` | Authenticated and a member, but the role is too low |
| `404` | Does not exist, **or** exists and the caller may not see it |
| `409` | Conflict — duplicate member, last owner, name collision |
| `422` | Pydantic validation failure |
| `429` | Per-user AI rate limit exceeded |
| `503` | AI provider unreachable or not configured |

## Out of scope for this iteration

GitHub OAuth and PR creation, voice/video, and a Kubernetes deployment. Each is
tracked in the README roadmap rather than half-built here.
