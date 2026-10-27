import test from "node:test";
import assert from "node:assert/strict";
import {
  parseProject,
  parseProjects,
  isProjectId,
} from "../src/lib/api/project-contract.ts";

const project = {
  id: "4c78e1e5-8efe-4430-aada-6ade30e82164",
  name: "Contract test fixture",
  description: null,
  status: "active",
  created_at: "2026-10-26T10:00:00Z",
  updated_at: "2026-10-26T10:00:00Z",
};
test("accepts current ProjectRead fields and strips unrelated upstream fields", () => {
  assert.deepEqual(
    parseProject({ ...project, credential: "must not propagate" }),
    project,
  );
  assert.deepEqual(
    parseProjects([project, { ...project, status: "archived" }]).map(
      (row) => row.status,
    ),
    ["active", "archived"],
  );
});
test("rejects uncontracted statuses, missing fields and malformed dates or IDs", () => {
  for (const invalid of [
    null,
    [],
    { ...project, status: "READY" },
    { ...project, name: " " },
    { ...project, created_at: "tomorrow" },
    { ...project, description: undefined },
    { ...project, id: "../../healthz" },
  ])
    assert.throws(() => parseProject(invalid));
  assert.throws(() => parseProjects({ projects: [project] }));
  assert.throws(() => parseProjects([project, {}]));
  assert.equal(isProjectId("preview"), false);
});
