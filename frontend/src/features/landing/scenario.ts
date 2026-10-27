// Illustrative scenario for the landing page only. It is static, labeled as
// illustrative wherever it renders, and never touches the product API layer.
export type ArtifactKind = "intent" | "requirement" | "criterion" | "decision" | "contract" | "task" | "evaluation" | "diagnosis" | "pull";
export type Artifact = {
    id: string;
    kind: ArtifactKind;
    label: string;
    title: string;
    body: string;
    fields: [string, string][];
    tone?: "pass" | "fail" | "warn";
    x: number;
    y: number;
};
export const artifacts: Artifact[] = [
    { id: "INTENT", kind: "intent", label: "Change request", title: "Finance needs a monthly invoice export", body: "Billing admins download invoices for one month as CSV, without touching how invoices are issued.", fields: [["Repository", "acme/billing-service"], ["Base", "main @ 3f9c2e1"]], x: 0, y: 150 },
    { id: "REQ-014", kind: "requirement", label: "Requirement", title: "Export monthly invoices as CSV", body: "An authorized billing admin can export every invoice issued in a chosen calendar month.", fields: [["Version", "v3, locked"], ["Reviewer", "A. Mensah"], ["Status", "Locked before design"]], x: 270, y: 150 },
    { id: "AC-031", kind: "criterion", label: "Acceptance criterion", title: "Only invoices issued in the selected month", body: "Given invoices on 28 Feb and 1 Mar, exporting February returns only the 28 Feb invoice, using the account time zone.", fields: [["Verified by", "test_export_month_boundary"]], x: 540, y: 60 },
    { id: "AC-032", kind: "criterion", label: "Acceptance criterion", title: "Columns match the finance template", body: "The header row and column order match finance-template.csv exactly.", fields: [["Verified by", "test_export_columns"]], x: 540, y: 240 },
    { id: "ADR-006", kind: "decision", label: "Decision record", title: "Stream the export from the read replica", body: "Month exports can be large. Streaming from the replica keeps memory flat and leaves the primary database alone.", fields: [["Alternative", "Background job with an email link"], ["Consequence", "Replica lag of up to 5 s is acceptable"]], x: 810, y: 60 },
    { id: "CON-004", kind: "contract", label: "API contract", title: "GET /invoices/export?month=YYYY-MM", body: "Returns text/csv. 403 for non-admins, 422 for an invalid month.", fields: [["Kind", "API"], ["Response", "text/csv, streamed"]], x: 810, y: 240 },
    { id: "TASK-052", kind: "task", label: "Task", title: "Query invoices by month", body: "Repository query bounded by the account's local month.", fields: [["Status", "Done"], ["Paths", "billing/invoices/query.py"]], tone: "pass", x: 1080, y: 60 },
    { id: "TASK-053", kind: "task", label: "Task", title: "CSV endpoint and writer", body: "Streams rows through the CSV writer behind the admin permission.", fields: [["Depends on", "TASK-052"], ["Readiness", "Ready once TASK-052 is done"]], x: 1080, y: 240 },
    { id: "RUN-019 · 1", kind: "evaluation", label: "Attempt 1 evaluation", title: "Failed AC-031", body: "The February export included the invoice issued 1 Mar 00:30 in the account's time zone. The query compared UTC dates.", fields: [["AC-031", "FAIL"], ["AC-032", "PASS"]], tone: "fail", x: 1350, y: 60 },
    { id: "DIAG-1", kind: "diagnosis", label: "Diagnosis", title: "Month boundary used UTC", body: "Correction: convert the month bounds to the account time zone before querying. Scope narrowed to query.py.", fields: [["Failing", "AC-031"], ["Scope", "billing/invoices/query.py"]], tone: "warn", x: 1350, y: 240 },
    { id: "RUN-019 · 2", kind: "evaluation", label: "Attempt 2 evaluation", title: "Passed both criteria", body: "Independent evaluation re-ran the suite on the corrected change. Both acceptance criteria pass.", fields: [["AC-031", "PASS"], ["AC-032", "PASS"], ["Tests", "14 passed"]], tone: "pass", x: 1620, y: 150 },
    { id: "PR #128", kind: "pull", label: "Pull request", title: "Export monthly invoices as CSV", body: "The PR body carries the requirement, criteria, decision, run ID and test results for review.", fields: [["Branch", "agent/run-019-task-053"], ["Changed", "4 files"]], x: 1890, y: 150 },
];
export const links: [string, string][] = [
    ["INTENT", "REQ-014"], ["REQ-014", "AC-031"], ["REQ-014", "AC-032"], ["AC-031", "ADR-006"], ["AC-032", "CON-004"],
    ["ADR-006", "TASK-052"], ["CON-004", "TASK-053"], ["TASK-052", "TASK-053"], ["TASK-053", "RUN-019 · 1"],
    ["RUN-019 · 1", "DIAG-1"], ["DIAG-1", "RUN-019 · 2"], ["RUN-019 · 2", "PR #128"],
];
export const stages: { label: string; ids: string[]; note: string }[] = [
    { label: "Request", ids: ["INTENT"], note: "A plain change request against a connected repository." },
    { label: "Specify", ids: ["REQ-014", "AC-031", "AC-032"], note: "Reviewed, versioned and locked before any design starts." },
    { label: "Design", ids: ["ADR-006", "CON-004"], note: "Decisions and contracts trace back to the criteria they serve." },
    { label: "Plan", ids: ["TASK-052", "TASK-053"], note: "Tasks run only when their dependencies are done." },
    { label: "Evaluate", ids: ["RUN-019 · 1", "DIAG-1", "RUN-019 · 2"], note: "A failed criterion is diagnosed and corrected, then evaluated again." },
    { label: "Deliver", ids: ["PR #128"], note: "The pull request arrives with its evidence attached." },
];
