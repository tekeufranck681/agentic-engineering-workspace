# POWER evidence: application request through the capability runtime, ModelGateway and Nightshift (ENG-008, ENG-028)

*(per v2.0 evidence delta: timestamp, sanitized request, observed result, component, storage pointer)*

* **Generated (UTC):** 2026-10-27T10:28:59+00:00
* **Command:** `python -m app.modules.model_gateway.smoke` (backend host)
* **Application request:** `POST /requirements/analyze` on the FastAPI app (`app.main.create_app`, in-process ASGI client) with the canonical demo brief. M4's requirements service gets its model through the capability runtime as capability `requirements.analyze_input`.
* **Provider:** Nightshift at `http://172.21.112.253:8088/v1`; lane for `requirements.analyze_input`: `nvidia/nemotron-3.5-bolt-e4b`
* **Sanitization:** receipts only. Prompts and replies are recorded as SHA-256 and length; the file is checked for the runtime token before saving.
* **Verdict:** PASS

## API result

* **HTTP status:** 200
* **Requirements set:** `RSET-001` with 3 requirements
  * `REQ-001` (functional, must): Subscription activation upon payment confirmation
  * `REQ-002` (functional, must): Prevention of activation on payment failure
  * `REQ-003` (functional, must): Handling unconfirmed payments

## Capability invocations

| Capability | Version | Outcome | Model calls | Repairs | Retries | Answered by | Duration | Output SHA-256 |
|---|---|---|---|---|---|---|---|---|
| `requirements.analyze_input` | 1.0.0 | ok | 1 | 0 | 0 | `nvidia/nemotron-3.5-bolt-e4b` | 5757 ms | `7c780816d4ffce15…` |

## Model call receipts

| Capability | Requested | Answered by | Attribution | Runtime receipt | From cache | Outcome | Latency | Tokens in/out | Structured |
|---|---|---|---|---|---|---|---|---|---|
| `requirements.analyze_input` | `nvidia/nemotron-3.5-bolt-e4b` | `nvidia/nemotron-3.5-bolt-e4b` | runtime receipt | `rcpt_req_9tvdylm9` | False | ok | 5752 ms | 379/312 | LLMRequirementsAnalysis: valid |
