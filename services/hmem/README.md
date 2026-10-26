# hmem-service

The product's Meterless Engine (ENG-018): the official H-MEM reference, vendored unmodified (`vendor/`, see `vendor/VENDORED.md`), behind a thin zero-dependency HTTP API of our own (`server.ts`). Decision: `docs/decisions/adr-meterless-engine.md`; integration: `docs/decisions/engine-integration.md`.

- **One store per project**: `$HMEM_DATA_DIR/<project_id>/state.json` (rewritten per mutation) and `ledger.jsonl` (append-only). Project ids are lowercase letters, digits and dashes (our project UUIDs), so they cannot leave the data directory.
- **Single writer**: exactly one process per data directory.
- **Model-free**: no credentials, no mining endpoint. Model-assisted extraction stays in the backend behind ModelGateway.
- **Conformance in the build**: `docker build` runs `conformance/runner.ts` against `vendor/hmem/reference/src/index.ts`, the module the service serves. A failing check fails the build; `/healthz` reports the recorded scorecard.
- Runs with `tsx` (the reference uses TypeScript parameter properties, which Node's type stripping rejects). Sponsor code runs only in this container.

## Run

```bash
docker compose -f infra/docker-compose.yml up -d hmem     # 127.0.0.1:8099, volume hmemdata
# or
docker build -t aew-hmem:dev services/hmem && docker run -d -p 127.0.0.1:8099:8099 -v hmemdata:/data aew-hmem:dev
```

The backend reads `HMEM_BASE_URL` (default `http://127.0.0.1:8099`). Live check across two backend sessions and a restart: `backend/tests/integration/run_meterless_engine.sh`.

## API

JSON in and out; errors are `{"error": {"kind", "message"}}`. Records never include embeddings.

| Method and path | Does |
|---|---|
| `GET /healthz` | engine, engine version, vendored commit, conformance scorecard, number of project stores |
| `GET /projects/{projectId}/memories` | every record in the project's store, oldest first |
| `POST /projects/{projectId}/memories` | `add`: `content`, `source` (required), `type`, `layer`, `tags`, `confidence`, `provenance {origin, learnedAt, label, refs}`, `chatId`, `missionId`, `goalRunId` |
| `GET /projects/{projectId}/memories/{memoryId}` | one record |
| `POST /projects/{projectId}/query` | `query`, optional `topN` (1-20), `threshold` (0-1), `chatId`: the engine's `{memories: [{memory, relevance}], context, trace}` |
| `POST /projects/{projectId}/memories/{memoryId}/feedback` | `kind`: `helpful`, `not_helpful` or `wrong` |
| `GET /projects/{projectId}/memories/{memoryId}/history` | the memory's ledger entries |

Each request logs one JSON line: time, method, path, status, duration.
