import test from "node:test";
import assert from "node:assert/strict";
import { parseRequirements } from "../src/lib/api/requirements-contract.ts";
const set = { id: "RSET-001", project_id: "4c78e1e5-8efe-4430-aada-6ade30e82164", version: 1, status: "draft", summary: "Export invoices", assumptions: [], open_questions: [] };
const requirement = { id: "REQ-001", project_id: set.project_id, version: 1, status: "draft", title: "Export invoices", description: "Export a CSV for the selected month.", type: "functional", priority: "P0", trace: { ac_ids: ["AC-001"] } };
test("requirements response preserves real version and AC references while stripping extra fields", () => {
 const result = parseRequirements({ set: { ...set, secret: "omit" }, requirements: [requirement] });
 assert.deepEqual(result.set, set);
 assert.deepEqual(result.requirements[0], requirement);
});
test("requirements response rejects missing structures and invalid version data", () => {
 for (const invalid of [null, {}, { set, requirements: [{}] }, { set: { ...set, version: 0 }, requirements: [] }, { set: { ...set, assumptions: "none" }, requirements: [] }]) assert.throws(() => parseRequirements(invalid));
});
