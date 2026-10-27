import test from "node:test";
import assert from "node:assert/strict";
import { apiRequest, ApiError } from "../src/lib/api/client.ts";

test("mutations are never automatically retried and unknown outcomes remain explicit", async () => {
  const original = globalThis.fetch;
  let attempts = 0;
  try {
    globalThis.fetch = async () => {
      attempts++;
      throw new TypeError("network failure");
    };
    await assert.rejects(
      apiRequest("/projects", (value) => value, {
        method: "POST",
        body: { name: "Test fixture" },
      }),
      (error) =>
        error instanceof ApiError && error.uncertain && error.status === 0,
    );
    assert.equal(attempts, 1);
    globalThis.fetch = async () =>
      Response.json(
        { message: "Unavailable", uncertain: false },
        { status: 503 },
      );
    await assert.rejects(
      apiRequest("/projects", (value) => value, { method: "POST" }),
      (error) => error.uncertain === false,
    );
    globalThis.fetch = async () =>
      Response.json(
        { message: "Duplicate", uncertain: false },
        { status: 409 },
      );
    await assert.rejects(
      apiRequest("/projects", (value) => value, { method: "POST" }),
      (error) => error.status === 409 && !error.uncertain,
    );
  } finally {
    globalThis.fetch = original;
  }
});
test("a malformed success cannot be reported as a confirmed save", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => Response.json({}, { status: 201 });
    await assert.rejects(
      apiRequest(
        "/projects",
        () => {
          throw new Error("schema mismatch");
        },
        { method: "POST" },
      ),
      (error) => error.status === 502 && error.uncertain,
    );
    await assert.rejects(
      apiRequest("/projects", () => {
        throw new Error("schema mismatch");
      }),
      (error) => error.status === 502 && !error.uncertain,
    );
  } finally {
    globalThis.fetch = original;
  }
});
