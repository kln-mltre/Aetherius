/**
 * Cancelling a run.
 *
 * There is no Python twin: the Python engine runs on a machine, where a run goes to the end. On a
 * phone, leaving a screen is an ordinary event, and a run that ignores it keeps a hidden WebView
 * alive that nobody is watching.
 *
 * Three grains are covered because three are needed, and one alone would leave cancellation waiting
 * up to thirty seconds: between two steps, inside a `wait`, and inside a request in flight. The
 * fourth thing checked is the one that costs a leaked view if it is wrong — teardown still runs.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { RunCancelledError } from "../dist/errors.js";
import { CollectingSink } from "../dist/events/index.js";
import { registerDriver } from "../dist/runtime/drivers.js";
import { RunEngine } from "../dist/runtime/engine.js";

async function run(steps, options = {}) {
  const sink = new CollectingSink();
  const result = await new RunEngine().run(
    { aetherius: "1.0", name: "cancel.demo", act: "vector", steps },
    { ...options, sinks: [sink] },
  );
  return { result, events: sink.events };
}

test("a run cancelled between two steps stops there, failed and named", async () => {
  const controller = new AbortController();
  const pending = run(
    [
      { id: "one", action: "wait", ms: 20 },
      { id: "two", action: "set", value: "never" },
    ],
    { signal: controller.signal },
  );
  setTimeout(() => controller.abort(), 5);

  const { result } = await pending;
  assert.equal(result.status, "failed");
  assert.ok(result.cause instanceof RunCancelledError, `unexpected cause: ${result.cause}`);
  // No step is recorded for work that never started, and no `error` event claims something broke.
  assert.equal(result.step_results.length, 0);
  assert.deepEqual(result.outputs, {});
});

test("a wait is interrupted, not waited out", async () => {
  const controller = new AbortController();
  const started = Date.now();
  const pending = run([{ id: "nap", action: "wait", ms: 5000 }], { signal: controller.signal });
  setTimeout(() => controller.abort(), 20);

  const { result } = await pending;
  assert.equal(result.status, "failed");
  assert.ok(Date.now() - started < 1000, "the wait ran to completion");
});

test("a request in flight is dropped, and reported as cancelled rather than as a dead source", async () => {
  const controller = new AbortController();
  const slowFetch = (_url, init) =>
    new Promise((resolve, reject) => {
      const timer = setTimeout(() => resolve(response("late")), 5000);
      init?.signal?.addEventListener?.("abort", () => {
        clearTimeout(timer);
        reject(new Error("aborted"));
      });
    });

  const pending = run([{ id: "get", action: "http.request", url: "https://example.invalid/" }], {
    signal: controller.signal,
    fetch: slowFetch,
  });
  setTimeout(() => controller.abort(), 20);

  const { result } = await pending;
  // The distinction that matters: an aborted fetch looks exactly like a transport failure, and
  // calling it one would put "the source is down" on screen when the user simply left.
  assert.ok(result.cause instanceof RunCancelledError, `unexpected cause: ${result.cause}`);
});

test("cancelling before the run starts throws instead of setting a driver up", async () => {
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(
    () => run([{ id: "one", action: "set", value: 1 }], { signal: controller.signal }),
    RunCancelledError,
  );
});

test("teardown still runs, so a driver's resources are released", async () => {
  let torn = 0;
  registerDriver("vector", () => ({
    act: "vector",
    async setup() {},
    async teardown() {
      torn += 1;
    },
    async runStep() {
      await new Promise((resolve) => setTimeout(resolve, 200));
      return {};
    },
  }));

  try {
    const controller = new AbortController();
    const pending = run(
      [
        { id: "one", action: "set", value: 1 },
        { id: "two", action: "set", value: 2 },
      ],
      { signal: controller.signal },
    );
    setTimeout(() => controller.abort(), 20);
    const { result } = await pending;
    assert.equal(result.status, "failed");
    assert.equal(torn, 1, "the driver was never torn down");
  } finally {
    // The registry is module-level: leave it as it was found, or every later test runs on a stub.
    const { VectorDriver } = await import("../dist/acts/vector/driver.js");
    registerDriver("vector", (host) => new VectorDriver(host));
  }
});

test("a parked confirm is released by cancellation instead of waiting out its deadline", async () => {
  const { ApprovalRegistry } = await import("../dist/runtime/approvals.js");
  const controller = new AbortController();
  const started = Date.now();
  const pending = run(
    [{ id: "ask", action: "confirm", message: "Publish?", timeout_ms: 60000 }],
    { signal: controller.signal, approvals: new ApprovalRegistry() },
  );
  setTimeout(() => controller.abort(), 30);

  const { result } = await pending;
  assert.equal(result.status, "failed");
  assert.ok(Date.now() - started < 2000, "the run stayed parked");
});

function response(body) {
  return {
    status: 200,
    url: "https://example.invalid/",
    headers: { get: () => null, forEach: () => {} },
    text: async () => body,
  };
}
