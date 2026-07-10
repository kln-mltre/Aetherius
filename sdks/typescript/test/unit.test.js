/**
 * Unit tests for the transport layer — no daemon, native fetch stubbed. These run everywhere,
 * including a CI job without Python. Imports the compiled output (built by `npm test`).
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { eventsUrl, fetchRun, submitRun } from "../dist/transport.js";

test("eventsUrl derives a ws:// URL from the http base", () => {
  assert.equal(eventsUrl("http://127.0.0.1:8787", "abc"), "ws://127.0.0.1:8787/v1/runs/abc/events");
});

test("submitRun posts the Blueprint with the bearer token and returns the run id", async () => {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return new Response(JSON.stringify({ run_id: "run-123" }), { status: 202 });
  };
  try {
    const id = await submitRun("http://d", { aetherius: "1.0" }, { a: 1 }, {}, "tok");
    assert.equal(id, "run-123");
    assert.equal(calls[0].url, "http://d/v1/runs");
    assert.equal(calls[0].init.method, "POST");
    assert.equal(calls[0].init.headers.Authorization, "Bearer tok");
    assert.deepEqual(JSON.parse(calls[0].init.body).inputs, { a: 1 });
  } finally {
    globalThis.fetch = original;
  }
});

test("fetchRun maps the daemon DTO to a RunResult", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({ run_id: "r", status: "succeeded", outputs: { greeting: "hi" }, error: null }),
      { status: 200 },
    );
  try {
    const run = await fetchRun("http://d", "r");
    assert.equal(run.runId, "r");
    assert.equal(run.status, "succeeded");
    assert.deepEqual(run.outputs, { greeting: "hi" });
    assert.equal(run.error, null);
  } finally {
    globalThis.fetch = original;
  }
});

test("fetchRun throws on a non-ok response", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response("nope", { status: 404 });
  try {
    await assert.rejects(() => fetchRun("http://d", "missing"));
  } finally {
    globalThis.fetch = original;
  }
});
