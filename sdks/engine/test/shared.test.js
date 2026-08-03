/**
 * The act-agnostic actions: `set`, `assert`, `emit`, `wait`, `confirm`.
 *
 * They are exercised through a real run rather than called directly, because what matters is what
 * a Blueprint observes — the outputs a later step can read, and the events a UI receives.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { ActionError, StatusAssertionError, StepTimeoutError } from "../dist/errors.js";
import { CollectingSink } from "../dist/events/index.js";
import { RunEngine } from "../dist/runtime/engine.js";

async function run(steps, extra = {}, options = {}) {
  const sink = new CollectingSink();
  const result = await new RunEngine().run(
    { aetherius: "1.0", name: "shared.demo", act: "vector", steps, ...extra },
    { ...options, sinks: [sink] },
  );
  return { result, events: sink.events };
}

const outputs = (result, id) => result.step_results.find((s) => s.step_id === id).outputs;

test("set stores a rendered value the next step can read", async () => {
  const { result } = await run(
    [
      { id: "one", action: "set", value: "{{ [1, 2, 3] }}" },
      { id: "two", action: "set", value: "{{ steps.one.value | length }}" },
    ],
    { outputs: { total: "{{ steps.two.value }}" } },
  );
  assert.deepEqual(outputs(result, "one").value, [1, 2, 3]);
  assert.deepEqual(result.outputs, { total: 3 });
});

test("set without a value stores null, as Python does", async () => {
  const { result } = await run([{ id: "one", action: "set" }]);
  assert.equal(outputs(result, "one").value, null);
});

test("assert passes on a truthy condition and fails the run otherwise", async () => {
  const { result: ok } = await run([{ id: "check", action: "assert", condition: "{{ 'yes' }}" }]);
  assert.equal(ok.status, "success");

  const { result: ko } = await run([
    { id: "check", action: "assert", condition: "{{ 2 }}", message: "count must be a flag" },
  ]);
  assert.equal(ko.status, "failed");
  // The Aetherius truthiness rule, not JavaScript's: `2` is false in an assert.
  assert.equal(ko.error, "Expected HTTP 1, got 0 — <assert>\ncount must be a flag");
});

test("the default assert message is the raw condition, rendered — quirk and all", async () => {
  // Python composes `Assertion failed: {condition}` from the *raw* text and then renders the
  // message, so the expression is evaluated once more and its value lands in the error. Pinned
  // here because it is observable, and because "fixing" it on one engine would be a divergence.
  const { result } = await run([{ id: "check", action: "assert", condition: "{{ inputs.flag }}" }], {}, {
    inputs: { flag: "no" },
  });
  assert.equal(result.error, "Expected HTTP 1, got 0 — <assert>\nAssertion failed: no");
  assert.ok(new StatusAssertionError("x") instanceof Error);
});

test("emit publishes a progress event carrying the step id", async () => {
  const { events } = await run([{ id: "hello", action: "emit", message: "user {{ 1 + 1 }}" }]);
  const progress = events.filter((e) => e.type === "progress");
  assert.deepEqual(
    progress.map((e) => [e.step_id ?? null, e.message]),
    [
      [null, "run started: shared.demo"],
      ["hello", "user 2"],
    ],
  );
});

test("emit prefers `event` over `message`, like the Python handler", async () => {
  const { events } = await run([{ action: "emit", event: "LOGIN_SUCCESS", message: "ignored" }]);
  assert.equal(events.filter((e) => e.type === "progress")[1].message, "LOGIN_SUCCESS");
});

test("wait pauses for the requested time, and refuses an inverted range", async () => {
  const started = Date.now();
  const { result } = await run([{ id: "pause", action: "wait", ms: 25 }]);
  assert.equal(result.status, "success");
  assert.ok(Date.now() - started >= 20, "the run actually waited");

  const { result: bad } = await run([
    { id: "pause", action: "wait", min_ms: 100, max_ms: 10 },
  ]);
  assert.equal(bad.status, "failed");
  assert.match(bad.error, /max_ms \(10\) must be >= min_ms \(100\)/);
  assert.ok(new ActionError("x") instanceof Error);
});

test("wait draws its pause from [min_ms, max_ms] when no fixed duration is given", async () => {
  const started = Date.now();
  const { result } = await run([{ id: "pause", action: "wait", min_ms: 15, max_ms: 30 }]);
  const elapsed = Date.now() - started;
  assert.equal(result.status, "success");
  assert.ok(elapsed >= 10 && elapsed < 300, `unexpected pause: ${elapsed}ms`);
});

test("an unattended confirm applies its on_timeout policy at once, denying by default", async () => {
  const { result } = await run([{ id: "ask", action: "confirm", message: "Publish?" }]);
  assert.equal(result.status, "success");
  assert.deepEqual(outputs(result, "ask"), {
    approved: false,
    decision: "rejected",
    value: null,
    decided_by: "timeout",
  });
});

test("on_timeout: approve lets the guarded step through", async () => {
  const { result } = await run([
    { id: "ask", action: "confirm", message: "Publish?", on_timeout: "approve" },
    { id: "publish", action: "set", when: "{{ steps.ask.approved }}", value: "sent" },
  ]);
  assert.equal(outputs(result, "ask").approved, true);
  assert.equal(outputs(result, "publish").value, "sent");
});

test("on_timeout: fail:CODE fails the run and names the code", async () => {
  const { result } = await run([
    { id: "ask", action: "confirm", message: "Publish?", on_timeout: "fail:NO_ANSWER" },
  ]);
  assert.equal(result.status, "failed");
  assert.match(result.error, /confirm timed out awaiting a decision/);
  // The code survives all the way to the caller: it is the only machine-readable thing a Blueprint
  // author can put on a failure, and an application branches on it (see failure.test.js).
  assert.ok(result.cause instanceof StepTimeoutError);
  assert.equal(result.cause.code, "NO_ANSWER");
});

test("confirm's notification fields are read and ignored on this engine", async () => {
  // `channel`/`target` alert a notify channel on the Python engine. The embedded engine has none —
  // the application owns its notifications, and the decision surface is the modal itself. Ignoring
  // them rather than refusing keeps the promise "the same Blueprint on both engines".
  const { result } = await run([
    {
      id: "ask",
      action: "confirm",
      message: "Publish?",
      on_timeout: "approve",
      channel: "ntfy",
      target: "some-topic",
      level: "warning",
    },
  ]);
  assert.equal(result.status, "success");
  assert.equal(outputs(result, "ask").approved, true);
});

test("a rejected confirm skips the step it guards, without failing the run", async () => {
  const { result } = await run([
    { id: "ask", action: "confirm", message: "Publish?" },
    { id: "publish", action: "set", when: "{{ steps.ask.approved }}", value: "sent" },
  ]);
  assert.equal(result.status, "success");
  assert.equal(result.step_results[1].status, "skipped");
});

test("an action no driver dispatches fails with the action named", async () => {
  // `extract` as a standalone step: declared by the capability table, dispatched by neither
  // engine (PENDING_ACTIONS). Accepted at validation, refused here — same as Python.
  const { result } = await run([{ id: "pull", action: "extract", outputs: {} }]);
  assert.equal(result.status, "failed");
  assert.equal(result.error, "VectorDriver: unsupported action 'extract'");
});
