import test from "node:test";
import assert from "node:assert/strict";
import { parseDeliveries, parseRuns, isPullRequestUrl } from "../src/lib/api/delivery-contract.ts";

const delivery = {
  run_id: "RUN-001", task_id: "TASK-001", branch: "agent/task-001", base_sha: "a".repeat(40), commit_sha: "b".repeat(40),
  changed_paths: ["src/app.py"], pr_number: 12, pr_url: "https://github.com/acme/demo/pull/12", tests_passed: 4,
  evidence: [{ kind: "test_run", id: "EV-001" }],
};

test("deliveries parse from a list or a wrapped object", () => {
  assert.equal(parseDeliveries([delivery])[0].pr_number, 12);
  assert.equal(parseDeliveries({ deliveries: [delivery] })[0].evidence[0].id, "EV-001");
  assert.deepEqual(parseDeliveries(JSON.parse(JSON.stringify(parseDeliveries([delivery])))), parseDeliveries([delivery]));
});

test("only GitHub pull request URLs are accepted", () => {
  assert.ok(isPullRequestUrl("https://github.com/acme/demo/pull/3"));
  for (const url of ["http://github.com/acme/demo/pull/3", "https://evil.example/acme/demo/pull/3", "javascript:alert(1)", "https://github.com/acme/demo"])
    assert.equal(isPullRequestUrl(url), false);
  assert.throws(() => parseDeliveries([{ ...delivery, pr_url: "javascript:alert(1)" }]));
});

test("runs parse from RunListResponse and reject unknown statuses", () => {
  const run = { id: "RUN-001", project_id: "4c78e1e5-8efe-4430-aada-6ade30e82164", task_id: "TASK-001", attempt: 1, status: "succeeded", error: null };
  assert.equal(parseRuns({ runs: [run] })[0].status, "succeeded");
  assert.throws(() => parseRuns({ runs: [{ ...run, status: "PASS" }] }));
});
