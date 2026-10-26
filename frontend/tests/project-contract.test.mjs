import test from "node:test";
import assert from "node:assert/strict";
import {
  parseProject,
  parseProjects,
  isProjectId,
  parseProjectCreate,
  bindingFromUrl,
  parseBinding,
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

test("project creation validates the existing backend contract", () => {
  assert.deepEqual(
    parseProjectCreate({ name: "  Test project  ", description: " " }),
    { name: "Test project", description: null },
  );
  for (const value of [
    { name: " " },
    { name: "x".repeat(201) },
    { name: "ok", description: "x".repeat(5001) },
  ])
    assert.throws(() => parseProjectCreate(value));
});
test("repository forms accept GitHub identities without embedded credentials or invented SHAs", () => {
  const binding = bindingFromUrl(
    "https://github.com/example/demo-target.git",
    "main",
    "",
  );
  assert.equal(binding.base_sha, null);
  assert.equal(binding.html_url, "https://github.com/example/demo-target");
  assert.throws(() =>
    bindingFromUrl("https://token@github.com/example/demo-target", "main", ""),
  );
  assert.throws(() =>
    bindingFromUrl(
      "https://github.com.evil.test/example/demo-target",
      "main",
      "",
    ),
  );
  assert.throws(() =>
    bindingFromUrl(
      "https://github.com/example/demo-target/tree/main",
      "main",
      "",
    ),
  );
  assert.throws(() =>
    bindingFromUrl(
      "https://github.com/example/demo-target",
      "main",
      "not-a-sha",
    ),
  );
  assert.throws(() =>
    parseBinding({
      ...binding,
      id: project.id,
      project_id: project.id,
      full_name: "different/repo",
      status: "active",
      bound_at: project.created_at,
    }),
  );
});
