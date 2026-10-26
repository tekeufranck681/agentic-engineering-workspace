# POWER evidence: application request through ModelGateway and Nightshift (ENG-008)

*(per v2.0 evidence delta: timestamp, sanitized request, observed result, component, storage pointer)*

* **Generated (UTC):** 2026-10-26T16:59:03+00:00
* **Command:** `python -m app.modules.model_gateway.smoke` (backend host)
* **Application request:** `POST /requirements/analyze` on the FastAPI app (`app.main.create_app`, in-process ASGI client) with the canonical demo brief. M4's requirements service gets its model from the gateway as capability `requirements.analyze_input`.
* **Provider:** Nightshift at `http://10.100.206.253:8088/v1`; lane for `requirements.analyze_input`: `meterless/auto`
* **Sanitization:** receipts only. Prompts and replies are recorded as SHA-256 and length; the file is checked for the runtime token before saving.
* **Verdict:** PASS

## API result

* **HTTP status:** 200
* **Requirements set:** `RSET-001` with 6 requirements
  * `REQ-001` (functional, must): Payment Confirmation Before Activation
  * `REQ-002` (functional, must): Failed/Unconfirmed Payment Handling
  * `REQ-003` (non_functional, should): Idempotent Payment Processing
  * `REQ-004` (non_functional, must): Secure Payment Data Handling
  * `REQ-005` (functional, should): Subscription Status Consistency
  * `REQ-006` (non_functional, could): API Response Time for Payment Confirmation

## Model call receipts

| Capability | Requested | Answered by | Attribution | Runtime receipt | From cache | Outcome | Latency | Tokens in/out | Structured |
|---|---|---|---|---|---|---|---|---|---|
| `requirements.analyze_input` | `meterless/auto` | `nvidia/nemotron-3.5-lightning-30b-a3b` | runtime receipt | `rcpt_req_t3p0v1rc` | False | ok | 18894 ms | 372/1179 | LLMRequirementsAnalysis: valid |
