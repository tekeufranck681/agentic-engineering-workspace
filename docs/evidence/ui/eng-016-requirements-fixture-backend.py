# Test fixture backend for Requirements visual verification only.
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
P = "4c78e1e5-8efe-4430-aada-6ade30e82164"
project = {"id": P, "name": "Fixture: Billing service", "description": None, "status": "active", "created_at": "2026-10-26T10:00:00Z", "updated_at": "2026-10-26T10:00:00Z"}
def body(status, version):
    req = lambda i, t, d, ty, pr, acs: {"id": f"REQ-00{i}", "project_id": P, "title": t, "description": d, "version": 1, "status": status, "priority": pr, "type": ty, "trace": {"requirement_ids": [], "ac_ids": acs, "task_ids": [], "contract_ids": []}}
    return {"set": {"id": "RSET-001", "project_id": P, "version": version, "status": status, "summary": "Billing admins export one calendar month of invoices as CSV, bounded by the account's time zone, without changing how invoices are issued.", "assumptions": ["Every account has a configured time zone.", "Exports are limited to billing admins."], "open_questions": ["Should credit notes be included in the export?"]},
            "requirements": [req(1, "Export invoices for a selected month", "An authorized billing admin can download every invoice issued in a chosen calendar month as a CSV file.", "functional", "must", ["AC-001", "AC-002"]),
                             req(2, "Use the account time zone for month bounds", "The month boundary is computed in the account's configured time zone, not UTC.", "functional", "must", ["AC-003"]),
                             req(3, "Match the finance column template", "The CSV header and column order match finance-template.csv.", "non_functional", "should", ["AC-004"])]}
class H(BaseHTTPRequestHandler):
    def _send(self, b, code=200):
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(json.dumps(b).encode())
    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/requirements/set/RSET-001": return self._send(body("draft", 1))
        b = {"/projects": [project], f"/projects/{P}": project}.get(p)
        self._send(b if b is not None else {"detail": "nf"}, 200 if b is not None else 404)
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path.endswith("/approve"): return self._send(body("approved", 2))
        self._send({"detail": "nf"}, 404)
    def log_message(self, *a): pass
ThreadingHTTPServer(("127.0.0.1", 8799), H).serve_forever()
