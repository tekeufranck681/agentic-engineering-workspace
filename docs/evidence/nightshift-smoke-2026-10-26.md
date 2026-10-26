# NIGHTSHIFT_RUNTIME evidence: runtime smoke check (ENG-003)

*(per v2.0 evidence delta: timestamp, sanitized request, observed result, component, storage pointer)*

* **Generated (UTC):** 2026-10-26T15:57:49+00:00
* **Command:** `python -m app.modules.nightshift.smoke` (backend host)
* **Endpoint:** `http://10.100.206.253:8088/v1/models`
* **meterless-app:** `agentic-engineering-workspace`
* **Sanitization:** the runtime token is never written; the file is checked for it before saving. Prompts are recorded as SHA-256 only.
* **Verdict:** PASS

## Status probe (GET /v1/models)

* **State:** online (HTTP 200)
* **Latency:** 81 ms
* **Advertised ids:** 19 total, 6 `meterless/*`, 5 `nvidia/*`
* **Routing ids:** `meterless/auto`, `meterless/fast`, `meterless/deep`, `meterless/cheap`, `meterless/local`, `meterless/fusion`
* **NVIDIA ids:** `nvidia/nemotron-3.5-lightning-30b-a3b`, `nvidia/nemotron-3-ultra-550b-a55b`, `nvidia/nemotron-3-embed-1b`, `nvidia/nemotron-3.5-bolt-e4b`, `nvidia/nemotron-3.5-embed-1b`

## Chat completions (POST /v1/chat/completions)

| Lane requested | Status | Answered by | Attribution source | Receipt id | Latency | Tokens in/out | Reply check |
|---|---|---|---|---|---|---|---|
| `meterless/auto` | ok | `nvidia/nemotron-3.5-bolt-e4b` | runtime receipt | `rcpt_req_0tq8dguk` | 1339 ms | 20/6 | matched |
| `meterless/fast` | ok | `nvidia/nemotron-3.5-bolt-e4b` | runtime receipt | `rcpt_req_yu7xgmc0` | 678 ms | 20/6 | matched |
| `meterless/deep` | ok | `nvidia/nemotron-3.5-bolt-e4b` | runtime receipt | `rcpt_req_mxaahx1p` | 788 ms | 20/6 | matched |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | ok | `nvidia/nemotron-3.5-lightning-30b-a3b` | runtime receipt | `rcpt_req_1gk4c5zs` | 7835 ms | 28/198 | matched |

## Routing receipt shape

* **Fields present:** `app`, `cache`, `consensus`, `cost`, `decision_id`, `egress`, `from_cache`, `job`, `lineage`, `losers_reclaimed`, `mcp`, `mode`, `phases`, `privacy`, `provider_model`, `receipt`, `receipt_envelope`, `receipt_id`, `requested_model`, `requires_review`, `routed_model`, `savings`, `schema`, `scope`, `served`, `usage`, `winning_route`
* `e856062008e52070800e7983f5c43f3e15164f3b79a329b14bec63941d1fac16` (SHA-256 of the canonical receipt JSON)
* `ff45cafc6d5fe1228dae453c5a861e70219202c4fada6216cb8d96bbd6082d88` (SHA-256 of the canonical receipt JSON)
* `b1a93de176b9c1369deecc38c8eb83e6da93a74c99274c0c2534cf04e7509fa8` (SHA-256 of the canonical receipt JSON)
* `2e1cd4629e185a0b6959d3c4e7cdd9c945c5989d54aadf7e2c89393e22f9f40d` (SHA-256 of the canonical receipt JSON)

## Earlier runs the same day

Same runtime and smoke command with the three default lanes; rows copied from the console output and the evidence file each run wrote before being overwritten. Attribution comes from the receipt's `routed_model` in every row.

| Run (UTC) | `meterless/auto` | `meterless/fast` | `meterless/deep` |
|---|---|---|---|
| 15:44:44 | `nvidia/nemotron-3.5-bolt-e4b`, `rcpt_req_k3pdc1y7`, 1600 ms, 20/6 tokens | `nvidia/nemotron-3.5-bolt-e4b`, `rcpt_req_fwo4h4qg`, 613 ms | `nvidia/nemotron-3.5-bolt-e4b`, `rcpt_req_uhwre3r6`, 513 ms |
| 15:54:21 | `nvidia/nemotron-3.5-lightning-30b-a3b`, `rcpt_req_jg6yemw1`, 3409 ms, 28/184 tokens | `nvidia/nemotron-3.5-bolt-e4b`, `rcpt_req_9wb1fyx9`, 816 ms | `nvidia/nemotron-3.5-bolt-e4b`, `rcpt_req_cls39y5r`, 715 ms |

The same lane (`meterless/auto`) was served by different models ten minutes apart, so attribution must be read from each call's receipt, never inferred from the lane.
