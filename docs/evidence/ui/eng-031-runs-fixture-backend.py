# Test fixture backend for Agent Runs visual verification only.
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
P = "4c78e1e5-8efe-4430-aada-6ade30e82164"
project = {"id": P, "name": "Fixture: Billing service", "description": None, "status": "active", "created_at": "2026-10-26T10:00:00Z", "updated_at": "2026-10-26T10:00:00Z"}
run = {"id": "RUN-001", "project_id": P, "task_id": "TASK-053", "attempt": 1, "status": "succeeded", "error": None, "version": 4}
task = {"id": "TASK-053", "project_id": P, "version": 1, "status": "done", "title": "CSV endpoint and writer", "description": "fixture", "target_paths": ["billing/invoices/query.py"], "size": "m", "depends_on": [], "readiness": None, "blocking_reasons": [], "trace": {"requirement_ids": ["REQ-001"], "ac_ids": ["AC-001", "AC-002"], "task_ids": [], "contract_ids": []}}
V = lambda a, v, r: {"acceptance_criterion_id": a, "verdict": v, "reason": r, "evidence_ids": ["EV-7"]}
events = [
  ("run.loaded", {"task_id": "TASK-053", "ac_ids": ["AC-001", "AC-002"], "readiness": "ready", "blocking_reasons": [], "base_sha": "3f9c2e1", "max_attempts": 3}),
  ("run.status", {"status": "running"}),
  ("context.built", {"manifest_id": "CTX-1", "chars": 18234, "degraded": False, "unknowns": []}),
  ("implementation.applied", {"task_id": "TASK-053", "summary": "Add month filter and CSV writer", "written": ["billing/invoices/query.py", "billing/invoices/export.py"], "rejected": [], "self_check": "passed"}),
  ("run.status", {"status": "evaluating"}),
  ("evaluation.completed", {"attempt": 1, "passed": False, "verdicts": [V("AC-001", "FAIL", "February export included an invoice issued 1 Mar 00:30 local time."), V("AC-002", "PASS", "Columns match template.")]}),
  ("diagnosis.completed", {"attempt": 1, "failing_ac_ids": ["AC-001"], "cause": "Month boundary compared UTC dates", "required_change": "Convert month bounds to the account time zone", "narrowed_paths": ["billing/invoices/query.py"]}),
  ("run.status", {"status": "running"}),
  ("implementation.applied", {"task_id": "TASK-053", "summary": "Use account time zone for bounds", "written": ["billing/invoices/query.py"], "rejected": ["billing/models.py"], "self_check": "passed", "attempt": 2}),
  ("evaluation.completed", {"attempt": 2, "passed": True, "verdicts": [V("AC-001", "PASS", "Only February invoices exported."), V("AC-002", "PASS", "Columns match template.")]}),
  ("delivery.started", {"task_id": "TASK-053", "base_sha": "3f9c2e1"}),
  ("delivery.gates_passed", {"tests_passed": 14, "changed_paths": ["billing/invoices/query.py", "billing/invoices/export.py"]}),
  ("delivery.pr_opened", {"pr_number": 128, "pr_url": "https://github.com/example-org/billing-service/pull/128", "branch": "agent/run-001-task-053", "commit_sha": "9a7b51d"}),
  ("run.finished", {"status": "succeeded", "attempts": 2}),
]
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        path, _, q = self.path.partition("?")
        if path.endswith("/events/stream"):
            after = int(dict(x.split("=") for x in q.split("&") if "=" in x).get("after", 0))
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            for i, (t, p) in enumerate(events, start=1):
                if i > after:
                    self.wfile.write(f"id: {i}\nevent: {t}\ndata: {json.dumps(p)}\n\n".encode())
            self.wfile.write(b'event: run_finished\ndata: {"run_id":"RUN-001","status":"succeeded"}\n\n')
            return
        body = {"/projects": [project], f"/projects/{P}": project, "/runs": {"runs": [run]}, "/runs/RUN-001": {"run": run, "task": task}}.get(path)
        self.send_response(200 if body is not None else 404); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(body if body is not None else {"detail": "nf"}).encode())
    def log_message(self, *a): pass
ThreadingHTTPServer(("127.0.0.1", 8799), H).serve_forever()
