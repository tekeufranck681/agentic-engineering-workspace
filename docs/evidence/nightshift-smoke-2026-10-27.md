# NIGHTSHIFT_RUNTIME evidence: runtime smoke check (ENG-003)

*(per v2.0 evidence delta: timestamp, sanitized request, observed result, component, storage pointer)*

* **Generated (UTC):** 2026-10-27T10:27:47+00:00
* **Command:** `python -m app.modules.nightshift.smoke` (backend host)
* **Endpoint:** `http://172.21.112.253:8088/v1/models`
* **meterless-app:** `agentic-engineering-workspace`
* **Sanitization:** the runtime token is never written; the file is checked for it before saving. Prompts are recorded as SHA-256 only.
* **Verdict:** PASS

## Status probe (GET /v1/models)

* **State:** online (HTTP 200)
* **Latency:** 45 ms
* **Advertised ids:** 19 total, 6 `meterless/*`, 5 `nvidia/*`
* **Routing ids:** `meterless/auto`, `meterless/fast`, `meterless/deep`, `meterless/cheap`, `meterless/local`, `meterless/fusion`
* **NVIDIA ids:** `nvidia/nemotron-3.5-lightning-30b-a3b`, `nvidia/nemotron-3-ultra-550b-a55b`, `nvidia/nemotron-3-embed-1b`, `nvidia/nemotron-3.5-bolt-e4b`, `nvidia/nemotron-3.5-embed-1b`

## Chat completions (POST /v1/chat/completions)

| Lane requested | Status | Answered by | Attribution source | Receipt id | Latency | Tokens in/out | Reply check |
|---|---|---|---|---|---|---|---|
| `meterless/auto` | ok | `nvidia/nemotron-3.5-lightning-30b-a3b` | runtime receipt | `rcpt_req_j3rjhaqv` | 25 ms | 13/4 | matched |
| `meterless/fast` | ok | `nvidia/nemotron-3.5-lightning-30b-a3b` | runtime receipt | `rcpt_req_4y1lpelk` | 19 ms | 13/4 | matched |
| `meterless/deep` | ok | `nvidia/nemotron-3.5-lightning-30b-a3b` | runtime receipt | `rcpt_req_cbn3gl4x` | 21 ms | 13/4 | matched |

## Routing receipt shape

* **Fields present:** `app`, `cache`, `cost`, `decision_id`, `from_cache`, `job`, `losers_reclaimed`, `mcp`, `mode`, `privacy`, `provider_model`, `receipt`, `receipt_envelope`, `receipt_id`, `requested_model`, `requires_review`, `routed_model`, `savings`, `schema`, `scope`, `served`, `usage`, `winning_route`
* `8b655867befaf606a2e2fc83439e8fe471fa7404169479187a48efb66074b150` (SHA-256 of the canonical receipt JSON)
* `ca957690b19873da4c58cae52db5d704ff45db4719765a20cc435be6dd16c41b` (SHA-256 of the canonical receipt JSON)
* `4e6e62467fbf5916af6ade72827e12f5d1ce40ae533bd9bb1173bb06364e4eb5` (SHA-256 of the canonical receipt JSON)
