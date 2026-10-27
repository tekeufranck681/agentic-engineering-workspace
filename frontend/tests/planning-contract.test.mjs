import test from "node:test";
import assert from "node:assert/strict";
import { parsePlan, parseReadiness } from "../src/lib/api/planning-contract.ts";

const projectId = "4c78e1e5-8efe-4430-aada-6ade30e82164";
const task = (id, depends_on = [], extra = {}) => ({
  id, project_id: projectId, version: 1, status: "pending", title: `Task ${id}`, description: "Contract test fixture",
  size: "s", depends_on, trace: { requirement_ids: ["REQ-001"], ac_ids: ["AC-001"], task_ids: [], contract_ids: [] }, ...extra,
});

test("plans parse tasks, trace links and dependency edges", () => {
  const plan = parsePlan({ tasks: [task("TASK-001"), task("TASK-002", ["TASK-001"])], dependencies: [{ task_id: "TASK-002", depends_on_id: "TASK-001" }] });
  assert.equal(plan.tasks.length, 2);
  assert.deepEqual(plan.tasks[1].ac_ids, ["AC-001"]);
  assert.equal(plan.tasks[0].readiness, null);
  assert.deepEqual(plan.dependencies, [{ task_id: "TASK-002", depends_on_id: "TASK-001" }]);
});

test("plan parsing is idempotent because the proxy and the client both parse", () => {
  const once = parsePlan({ tasks: [task("TASK-001"), task("TASK-002", ["TASK-001"])] });
  assert.deepEqual(parsePlan(JSON.parse(JSON.stringify(once))), once);
});

test("uncontracted task statuses and readiness values are rejected", () => {
  assert.throws(() => parsePlan({ tasks: [task("TASK-001", [], { status: "DONE" })] }));
  assert.throws(() => parsePlan({ tasks: [task("TASK-001", [], { readiness: "maybe" })] }));
  assert.throws(() => parseReadiness({ task_id: "TASK-001", readiness: "unknown", blocking_reasons: [] }));
  assert.deepEqual(parseReadiness({ task_id: "TASK-002", readiness: "blocked", blocking_reasons: ["dependency TASK-001 (x) is pending"] }).blocking_reasons.length, 1);
});
