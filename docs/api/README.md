# API documentation

| File | What it is |
|---|---|
| `ai-collab-contract.md` | The contract. Written before the implementation, and what the code is held to. |
| `openapi.json` | Generated from the running app. CI fails if it drifts from the code. |
| `postman/` | A runnable check of the contract - 28 requests, 60 assertions. |

## Regenerating the OpenAPI spec

Run this after adding, removing, or changing any endpoint. CI compares the
committed file against what the app actually serves, so a stale spec fails the
build rather than quietly misleading whoever reads it.

```bash
cd server
SECRET_KEY=dev EXECUTION_BACKEND=disabled python -c "
import json
from app.main import app
with open('../docs/api/openapi.json', 'w', encoding='utf-8') as f:
    json.dump(app.openapi(), f, indent=2)
print(len(app.openapi()['paths']), 'paths')
"
```

## Running the Postman collection

Import `postman/ai-collab-platform.postman_collection.json` and run the folders
in order - each stores the ids the next one needs. Set `baseUrl` if the API is
not on `http://127.0.0.1:8000`.

From the command line with [newman](https://github.com/postmanlabs/newman):

```bash
npx newman run docs/api/postman/ai-collab-platform.postman_collection.json \
  --env-var baseUrl=http://127.0.0.1:8000
```

The collection asserts the rules that are easy to regress without noticing:

- `404` - not `403` - for a resource the caller has no relationship to, so the
  API never confirms that something exists to someone with no access to it.
- `403` only once the caller is a member whose role is too low.
- `409` for searching a project that has not been indexed.
- Project files stay untouched until a fix run is explicitly approved.
