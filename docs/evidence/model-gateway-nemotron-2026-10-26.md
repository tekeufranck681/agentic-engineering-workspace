# POWER evidence: application request through ModelGateway and Nightshift (ENG-008)

*(per v2.0 evidence delta: timestamp, sanitized request, observed result, component, storage pointer)*

* **Generated (UTC):** 2026-10-26T16:59:44+00:00
* **Command:** `python -m app.modules.model_gateway.smoke` (backend host)
* **Application request:** `POST /requirements/analyze` on the FastAPI app (`app.main.create_app`, in-process ASGI client) with the canonical demo brief. M4's requirements service gets its model from the gateway as capability `requirements.analyze_input`.
* **Provider:** Nightshift at `http://10.100.206.253:8088/v1`; lane for `requirements.analyze_input`: `nvidia/nemotron-3.5-lightning-30b-a3b`
* **Sanitization:** receipts only. Prompts and replies are recorded as SHA-256 and length; the file is checked for the runtime token before saving.
* **Verdict:** PASS

## API result

* **HTTP status:** 200
* **Requirements set:** `RSET-001` with 5 requirements
  * `REQ-001` (functional, must): Activate subscription only after payment confirmation
  * `REQ-002` (functional, must): Reject subscription activation on payment failure
  * `REQ-003` (functional, should): Record payment transaction ID
  * `REQ-004` (non_functional, should): Idempotent payment confirmation handling
  * `REQ-005` (non_functional, could): Data consistency across services

## Model call receipts

| Capability | Requested | Answered by | Attribution | Runtime receipt | From cache | Outcome | Latency | Tokens in/out | Structured |
|---|---|---|---|---|---|---|---|---|---|
| `requirements.analyze_input` | `nvidia/nemotron-3.5-lightning-30b-a3b` | `nvidia/nemotron-3.5-lightning-30b-a3b` | runtime receipt | `rcpt_req_jte0jhzn` | False | ok | 39410 ms | 336/1639 | LLMRequirementsAnalysis: valid |
