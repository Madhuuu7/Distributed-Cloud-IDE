# Distributed Cloud IDE

A browser-based cloud IDE: create projects, edit files in Monaco, and run code
inside a throwaway, network-isolated Docker container.

## Stack

**Frontend** React, Vite, TypeScript, Tailwind CSS, React Router, Axios, Monaco Editor

**Backend** FastAPI, SQLAlchemy, SQLite, JWT authentication, Pydantic, Uvicorn, Docker SDK

## Security model

**Authentication.** Every endpoint except `/health`, `/auth/login`, and
`/auth/signup` requires a bearer token. The token is resolved to a `User` by the
`get_current_user` dependency, and every project and file query is scoped to
that user's `owner_id`. Requesting another user's resource returns `404` rather
than `403`, so the API never confirms that a resource exists.

**Code execution.** Each submission runs in a fresh container that is destroyed
afterwards. The container has:

| Control | Setting |
|---|---|
| Network | disabled entirely |
| Root filesystem | read-only, with a 32 MB `tmpfs` at `/tmp` for scratch |
| User | `65534:65534` (unprivileged) |
| Capabilities | all dropped, `no-new-privileges` |
| Memory | 256 MB, swap disabled (`memswap_limit == mem_limit`) |
| CPU | 0.5 cores |
| Processes | 64 PID ceiling |
| Wall clock | 10 s, then killed |
| Output | truncated at 64 KB |

Every limit is configurable via environment variables — see `.env.example`.

Setting `EXECUTION_BACKEND=local` replaces this with a bare subprocess on the
host. That path has **no isolation** and exists only so the app runs on machines
without a Docker daemon. The API logs a warning at startup when it is active.

> The API talks to the Docker socket directly to spawn sibling containers, which
> grants it host-level Docker control. That is fine for local development; in
> production, execution belongs in a separate worker behind a queue rather than
> in the public-facing API.

## Getting started

Copy `.env.example` to `.env` and set a real `SECRET_KEY`.

### Backend

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r server/requirements.txt

cd server
uvicorn app.main:app --reload --port 8000
```

Interactive API docs: <http://localhost:8000/docs>

The Python and Node runtime images are pulled automatically on first use, so the
first run of each language takes a few extra seconds. Pre-pull them to skip that:

```bash
docker pull python:3.12-slim
docker pull node:20-alpine
```

### Frontend

```bash
cd client
npm install
npm run dev
```

### Everything at once

```bash
docker compose up --build
```

## Tests

```bash
cd server
pip install -r requirements-dev.txt
pytest
```

The suite covers authentication enforcement, cross-user isolation, and the
execution engine. Execution tests default to `EXECUTION_BACKEND=local` so they
pass without a Docker daemon; the container arguments themselves are asserted
against a fake Docker client, so loosening a sandbox flag fails a test. To
exercise the real sandbox end to end:

```bash
EXECUTION_BACKEND=docker pytest tests/test_execution.py
```

## API

| Method | Path | Notes |
|---|---|---|
| `POST` | `/auth/signup` | Returns a bearer token |
| `POST` | `/auth/login` | Returns a bearer token |
| `GET` | `/auth/me` | Current user |
| `GET` `POST` | `/projects` | Scoped to the caller |
| `GET` `DELETE` | `/projects/{id}` | Deleting removes the project's files |
| `GET` `POST` | `/projects/{id}/files` | Language inferred from the extension |
| `GET` `PUT` `DELETE` | `/projects/file/{id}` | |
| `GET` | `/execute/languages` | Supported runtimes |
| `POST` | `/execute` | Returns stdout, stderr, exit code, duration |
| `GET` | `/health` | Public |

## Roadmap

Built: authentication, project and file management, Monaco editor, sandboxed
Python and JavaScript execution.

Next: WebSocket streaming for live output, xterm.js interactive terminal,
real-time collaborative editing (Yjs), PostgreSQL migration, AI assistant panel,
Git integration, Kubernetes manifests.
