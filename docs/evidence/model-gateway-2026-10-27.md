# POWER evidence: application request through the capability runtime, ModelGateway and Nightshift (ENG-008, ENG-028)

*(per v2.0 evidence delta: timestamp, sanitized request, observed result, component, storage pointer)*

* **Generated (UTC):** 2026-10-27T10:28:51+00:00
* **Command:** `python -m app.modules.model_gateway.smoke` (backend host)
* **Application request:** `POST /requirements/analyze` on the FastAPI app (`app.main.create_app`, in-process ASGI client) with the canonical demo brief. M4's requirements service gets its model through the capability runtime as capability `requirements.analyze_input`.
* **Provider:** Nightshift at `http://172.21.112.253:8088/v1`; lane for `requirements.analyze_input`: `meterless/auto`
* **Sanitization:** receipts only. Prompts and replies are recorded as SHA-256 and length; the file is checked for the runtime token before saving.
* **Verdict:** PASS

## API result

* **HTTP status:** 200
* **Requirements set:** `RSET-001` with 2 requirements
  * `REQ-001` (functional, must): Subscription Activation upon Payment Confirmation
  * `REQ-002` (functional, must): No Activation on Payment Failure/Unconfirmation

## Capability invocations

| Capability | Version | Outcome | Model calls | Repairs | Retries | Answered by | Duration | Output SHA-256 |
|---|---|---|---|---|---|---|---|---|
| `requirements.analyze_input` | 1.0.0 | ok | 1 | 0 | 0 | `nvidia/nemotron-3.5-bolt-e4b` | 3564 ms | `e65a5e3b1b508999…` |

## Model call receipts

| Capability | Requested | Answered by | Attribution | Runtime receipt | From cache | Outcome | Latency | Tokens in/out | Structured |
|---|---|---|---|---|---|---|---|---|---|
| `requirements.analyze_input` | `meterless/auto` | `nvidia/nemotron-3.5-bolt-e4b` | runtime receipt | `rcpt_req_0cfnkoa2` | False | ok | 3558 ms | 414/199 | LLMRequirementsAnalysis: valid |
