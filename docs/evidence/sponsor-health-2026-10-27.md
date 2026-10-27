# SPONSOR_READY evidence: integration health smoke (ENG-042)

*(per v2.0 evidence delta: timestamp, sanitized request, observed result, component/version, storage pointer; no keys or tokens)*

* **Generated (UTC):** 2026-10-27T09:52:42.399108+00:00
* **Command:** `python -m app.modules.integrations.smoke`
* **Overall:** `verified`
* **Sanitization:** bearer secrets are scrubbed; the file is checked for configured token values before it is written.

## Checks

| Sponsor | Runtime | Status | Detail | Last success (UTC) |
|---|---|---|---|---|
| `zetaris` | yes | `verified` | governed REST query returned real rows with grounded evidence | 2026-10-27T09:52:42.361959+00:00 |
| `nightshift` | yes | `verified` | authenticated model discovery succeeded | 2026-10-27T09:52:42.385386+00:00 |
| `meterless_engine` | yes | `verified` | engine sidecar healthy; vendored engine and conformance scorecard reported | 2026-10-27T09:52:42.399050+00:00 |
| `cursor` | no | `not_checked` | Cursor is build-time provenance, not a runtime service; record CURSOR_BUILD evidence in docs/evidence/ and the submission narrative (ENG-057) | never in this process |

## Provenance (sanitized)

```json
{
  "checks": [
    {
      "checked_at": "2026-10-27T09:52:42.362017Z",
      "detail": "governed REST query returned real rows with grounded evidence",
      "display_name": "Zetaris governed data layer",
      "last_success": {
        "at": "2026-10-27T09:52:42.361959Z",
        "provenance": {
          "datasources": [
            "aew_pg"
          ],
          "duration_ms": 7188,
          "endpoint": "http://localhost:8888/api/v1.0/sql-editor/sqls/run",
          "lightning_database_count": 3,
          "org_id": "1",
          "query_id": "4a3dc818-1cf3-4bc6-a653-88ed8caf4851",
          "request_id": "9956cfd3-8e33-4b54-a2dd-7601d548747c",
          "truth_row_count": 5,
          "truth_statement": "SELECT * FROM NY_TAXI.customers LIMIT 5"
        }
      },
      "latency_ms": 7188,
      "provenance": {
        "datasources": [
          "aew_pg"
        ],
        "duration_ms": 7188,
        "endpoint": "http://localhost:8888/api/v1.0/sql-editor/sqls/run",
        "lightning_database_count": 3,
        "org_id": "1",
        "query_id": "4a3dc818-1cf3-4bc6-a653-88ed8caf4851",
        "request_id": "9956cfd3-8e33-4b54-a2dd-7601d548747c",
        "truth_row_count": 5,
        "truth_statement": "SELECT * FROM NY_TAXI.customers LIMIT 5"
      },
      "runtime": true,
      "sponsor": "zetaris",
      "status": "verified"
    },
    {
      "checked_at": "2026-10-27T09:52:42.385436Z",
      "detail": "authenticated model discovery succeeded",
      "display_name": "Meterless Nightshift runtime",
      "last_success": {
        "at": "2026-10-27T09:52:42.385386Z",
        "provenance": {
          "endpoint": "http://127.0.0.1:8088/v1/models",
          "http_status": 200,
          "latency_ms": 11,
          "meterless_lanes": [
            "meterless/auto",
            "meterless/fast",
            "meterless/deep",
            "meterless/cheap",
            "meterless/local",
            "meterless/fusion",
            "meterless/cluster",
            "meterless/text",
            "meterless/code",
            "meterless/vision",
            "meterless/perception",
            "meterless/image",
            "meterless/video",
            "meterless/speech",
            "meterless/transcribe",
            "meterless/music",
            "meterless/embed",
            "meterless/judge"
          ],
          "model_count": 79
        }
      },
      "latency_ms": 11,
      "provenance": {
        "endpoint": "http://127.0.0.1:8088/v1/models",
        "http_status": 200,
        "latency_ms": 11,
        "meterless_lanes": [
          "meterless/auto",
          "meterless/fast",
          "meterless/deep",
          "meterless/cheap",
          "meterless/local",
          "meterless/fusion",
          "meterless/cluster",
          "meterless/text",
          "meterless/code",
          "meterless/vision",
          "meterless/perception",
          "meterless/image",
          "meterless/video",
          "meterless/speech",
          "meterless/transcribe",
          "meterless/music",
          "meterless/embed",
          "meterless/judge"
        ],
        "model_count": 79
      },
      "runtime": true,
      "sponsor": "nightshift",
      "status": "verified"
    },
    {
      "checked_at": "2026-10-27T09:52:42.399071Z",
      "detail": "engine sidecar healthy; vendored engine and conformance scorecard reported",
      "display_name": "Meterless Engine (H-MEM)",
      "last_success": {
        "at": "2026-10-27T09:52:42.399050Z",
        "provenance": {
          "conformance": {
            "passed": 13,
            "total": 13
          },
          "engine": "meterless-hmem",
          "engine_version": "0.1.0",
          "projects": 0,
          "sidecar_status": "ok",
          "vendored_sha": "1742dec56a66e58eef9dda2d2b865823758ca8cd"
        }
      },
      "latency_ms": null,
      "provenance": {
        "conformance": {
          "passed": 13,
          "total": 13
        },
        "engine": "meterless-hmem",
        "engine_version": "0.1.0",
        "projects": 0,
        "sidecar_status": "ok",
        "vendored_sha": "1742dec56a66e58eef9dda2d2b865823758ca8cd"
      },
      "runtime": true,
      "sponsor": "meterless_engine",
      "status": "verified"
    },
    {
      "checked_at": "2026-10-27T09:52:42.399104Z",
      "detail": "Cursor is build-time provenance, not a runtime service; record CURSOR_BUILD evidence in docs/evidence/ and the submission narrative (ENG-057)",
      "display_name": "Cursor build provenance",
      "last_success": null,
      "latency_ms": null,
      "provenance": {},
      "runtime": false,
      "sponsor": "cursor",
      "status": "not_checked"
    }
  ],
  "generated_at": "2026-10-27T09:52:42.399108Z",
  "overall": "verified"
}
```

Cursor is intentionally `not_checked`: it is build-time provenance (CURSOR_BUILD evidence), not a runtime service.
