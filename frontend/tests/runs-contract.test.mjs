import test from "node:test";
import assert from "node:assert/strict";
import { mergeEvents, parseEvent, verdictsOf } from "../src/lib/api/run-events.ts";

test("events merge in sequence order and replays after a reconnect never duplicate", () => {
  const a = parseEvent("1", "run.loaded", '{"task_id":"TASK-001"}');
  const b = parseEvent("2", "evaluation.completed", '{"attempt":1,"passed":false}');
  const c = parseEvent(3, "diagnosis.completed", '{"attempt":1,"cause":"x"}');
  const merged = mergeEvents(mergeEvents([a, c], [b]), [a, b, c]);
  assert.deepEqual(merged.map((e) => e.sequence), [1, 2, 3]);
});

test("malformed frames are dropped rather than shown", () => {
  assert.equal(parseEvent("0", "run.loaded", "{}"), null);
  assert.equal(parseEvent("x", "run.loaded", "{}"), null);
  assert.equal(parseEvent("4", "Run Loaded", "{}"), null);
  assert.equal(parseEvent("5", "run.loaded", "{not json"), null);
});

test("verdicts keep only contracted values", () => {
  const event = parseEvent("6", "evaluation.completed", JSON.stringify({ passed: false, verdicts: [
    { acceptance_criterion_id: "AC-001", verdict: "PASS", reason: "ok", evidence_ids: ["EV-1"] },
    { acceptance_criterion_id: "AC-002", verdict: "FAIL", reason: "wrong month" },
    { acceptance_criterion_id: "AC-003", verdict: "MAYBE" },
  ] }));
  assert.deepEqual(verdictsOf(event).map((v) => `${v.acceptance_criterion_id}:${v.verdict}`), ["AC-001:PASS", "AC-002:FAIL"]);
});
