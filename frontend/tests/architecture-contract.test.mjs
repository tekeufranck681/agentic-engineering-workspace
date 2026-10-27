import test from "node:test";
import assert from "node:assert/strict";
import { parseArchitecture } from "../src/lib/api/architecture-contract.ts";

const projectId = "4c78e1e5-8efe-4430-aada-6ade30e82164";
const body = {
  architecture: {
    id: "ARCH-001",
    project_id: projectId,
    version: 1,
    status: "draft",
    summary: "Contract test fixture",
    components: [
      { name: "API", responsibility: "Serves requests", depends_on: ["Store"], requirement_ids: ["REQ-001"] },
      { name: "Store", responsibility: "Persists records" },
    ],
    decision_ids: ["ADR-001"],
    derived_from: [{ kind: "requirements_set", id: "RSET-001", version: 1 }],
  },
  decisions: [
    { id: "ADR-001", project_id: projectId, version: 1, status: "draft", title: "Use SQL", context: "c", decision: "d" },
  ],
  contracts: [],
};

test("architecture responses parse components, decisions and lineage", () => {
  const result = parseArchitecture(body);
  assert.equal(result.architecture.components.length, 2);
  assert.deepEqual(result.architecture.components[1].depends_on, []);
  assert.deepEqual(result.architecture.derived_from, ["RSET-001"]);
  assert.deepEqual(result.decisions[0].alternatives, []);
  assert.deepEqual(result.contracts, []);
});

test("parsing is idempotent because the proxy and the client both parse", () => {
  const once = parseArchitecture(body);
  assert.deepEqual(parseArchitecture(JSON.parse(JSON.stringify(once))).architecture, once.architecture);
});

test("engineering contracts are summarized by kind", () => {
  const result = parseArchitecture({
    ...body,
    contracts: [{ id: "CON-001", project_id: projectId, version: 1, status: "draft", content: { kind: "api", endpoints: [{}, {}] } }],
  });
  assert.equal(result.contracts[0].summary, "2 API endpoint(s)");
  assert.deepEqual(parseArchitecture(JSON.parse(JSON.stringify(result))).contracts, result.contracts);
});

test("malformed architecture responses are rejected", () => {
  assert.throws(() => parseArchitecture({ architecture: { ...body.architecture, components: "API" }, decisions: [] }));
  assert.throws(() => parseArchitecture({ ...body, architecture: { ...body.architecture, version: 0 } }));
  assert.throws(() => parseArchitecture({ ...body, contracts: [{ ...body.decisions[0], content: { kind: "other" } }] }));
});
