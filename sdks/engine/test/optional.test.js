/**
 * The `optional` block (milestone 3-J), mirror of `tests/unit/core/runtime/test_optional.py`.
 *
 * The block is the only thing in the engine that turns a step failure into something other than a
 * dead run, so what is pinned here is the whole contract: the failing step keeps its `failed` and
 * its event, the rest of the block is `skipped`, the block itself is `partial`, and the run carries
 * on — to finish `partial`, with its outputs rendered.
 *
 * The conformance corpus proves the two engines agree; these tests state what the agreement *is*.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { ActionError, BlueprintValidationError, RunCancelledError, TemplateError } from "../dist/errors.js";
import { CollectingSink } from "../dist/events/index.js";
import { RunEngine, registerDriver } from "../dist/index.js";

/** An Act made of one driver that fails on the step named `fail`. */
function recorder({ fail } = {}) {
  return {
    act: "vector",
    setup: async () => {},
    teardown: async () => {},
    runStep: async (step) => {
      if (fail !== undefined && step.id === fail) throw new ActionError(`boom: ${step.id}`);
      return { value: step["value"] ?? null };
    },
  };
}

async function run(steps, { outputs, fail = "bad", ...options } = {}) {
  const sink = new CollectingSink();
  const { VectorDriver } = await import("../dist/acts/vector/driver.js");
  registerDriver("vector", () => recorder({ fail }));
  const document = { aetherius: "1.0", name: "optional.demo", act: "vector", steps };
  if (outputs !== undefined) document.outputs = outputs;
  try {
    const result = await new RunEngine().run(document, { ...options, sinks: [sink] });
    return { result, events: sink.events };
  } finally {
    registerDriver("vector", (host) => new VectorDriver(host));
  }
}

const statuses = (result) => result.step_results.map((s) => [s.step_id, s.status]);
const BOOM = { id: "bad", action: "set", value: 1 };

test("a block that fully succeeds tints nothing", async () => {
  const { result } = await run([
    { id: "blk", action: "optional", steps: [{ id: "a", action: "set", value: 1 }] },
  ]);
  assert.equal(result.status, "success");
  assert.deepEqual(statuses(result), [
    ["blk.a", "success"],
    ["blk", "success"],
  ]);
});

test("a block that gives way skips the rest and the run carries on", async () => {
  const { result, events } = await run([
    { id: "before", action: "set", value: "read" },
    {
      id: "blk",
      action: "optional",
      steps: [
        { id: "one", action: "set", value: 1 },
        BOOM,
        { id: "three", action: "set", value: 3 },
        { id: "four", action: "set", value: 4 },
      ],
    },
    { id: "after", action: "set", value: "still here" },
  ]);

  assert.equal(result.status, "partial");
  assert.deepEqual(statuses(result), [
    ["before", "success"],
    ["blk.one", "success"],
    ["blk.bad", "failed"],
    ["blk.three", "skipped"],
    ["blk.four", "skipped"],
    ["blk", "partial"],
    ["after", "success"],
  ]);

  // The failure stays visible: one error event, on the step that carried it.
  assert.deepEqual(
    events.filter((e) => e.type === "error").map((e) => e.step_id),
    ["blk.bad"],
  );
  // A partial run is not a failure: no run-level error, no cause, and `done` is not an error.
  assert.equal(result.error, undefined);
  assert.equal(result.cause, undefined);
  const done = events.find((e) => e.type === "done");
  assert.equal(done.data.status, "partial");
  assert.equal(done.level, "info");
});

test("a hard failure always wins over a tolerated one", async () => {
  // Alone, the block that gave way leaves the run partial...
  const tolerated = await run([{ action: "optional", steps: [BOOM] }]);
  assert.equal(tolerated.result.status, "partial");

  // ...but no tolerance leaks outside the braces: a failure after the block kills the run.
  const { result } = await run([
    { action: "optional", steps: [BOOM] },
    { id: "bad", action: "set" },
  ]);
  assert.equal(result.status, "failed");
});

test("skipped steps of a block say why, and keep their position", async () => {
  const { result, events } = await run([
    {
      id: "blk",
      action: "optional",
      steps: [{ action: "set" }, BOOM, { action: "set" }, { action: "set" }],
    },
  ]);
  // An anonymous step skipped in third position is `_step_2`, never `_step_0`.
  assert.deepEqual(statuses(result), [
    ["blk._step_0", "success"],
    ["blk.bad", "failed"],
    ["blk._step_2", "skipped"],
    ["blk._step_3", "skipped"],
    ["blk", "partial"],
  ]);
  const skipped = events.filter((e) => e.type === "step_skipped");
  // Worded identically in the Python engine, and distinct from a `when` guard.
  assert.equal(skipped[0].message, "skipped: an earlier step of the optional block failed");
});

test("a partial run still renders its outputs", async () => {
  const { result } = await run(
    [
      { id: "identity", action: "set", value: "read before the block" },
      { action: "optional", steps: [BOOM, { id: "bonus", action: "set", value: "x" }] },
    ],
    { outputs: { identity: "{{ steps.identity.value }}", bonus: "{{ steps.bonus.value | default(none) }}" } },
  );
  assert.equal(result.status, "partial");
  assert.deepEqual(result.outputs, { identity: "read before the block", bonus: null });
});

test("steps of a block that produced nothing are seeded empty, at any depth", async () => {
  // Without the seeding, `steps.coord.city | default(null)` would throw: both engines reject the
  // undefined at the point of use, so the filter never sees the value.
  const { result } = await run(
    [
      {
        action: "optional",
        steps: [
          {
            action: "for_each",
            items: "{{ [1, 2] }}",
            steps: [{ id: "coord", action: "set" }],
          },
        ],
      },
    ],
    { outputs: { city: "{{ steps.coord.city | default(none) }}" }, fail: "coord" },
  );
  assert.equal(result.status, "partial");
  assert.deepEqual(result.outputs, { city: null });
});

test("seeding never overwrites what a step published", async () => {
  const { result } = await run(
    [{ action: "optional", steps: [{ id: "kept", action: "set", value: "first pass" }, BOOM] }],
    { outputs: { kept: "{{ steps.kept.value | default(none) }}" } },
  );
  assert.deepEqual(result.outputs, { kept: "first pass" });
});

test("an output without a default fails loudly", async () => {
  // The writing rule is a rule, not magic: forgetting it must break at the outputs.
  await assert.rejects(
    () =>
      run([{ action: "optional", steps: [BOOM, { id: "bonus", action: "set" }] }], {
        outputs: { bonus: "{{ steps.bonus.value }}" },
      }),
    TemplateError,
  );
});

test("tolerance does not climb out of the inner block", async () => {
  const { result } = await run([
    {
      id: "outer",
      action: "optional",
      steps: [
        { id: "inner", action: "optional", steps: [BOOM] },
        { id: "after", action: "set", value: "reached" },
      ],
    },
  ]);
  // Only the inner block gives way; the outer runs to the end and stays `success`. The *run* is
  // partial: that verdict is read from the results, never propagated.
  assert.deepEqual(statuses(result), [
    ["outer.inner.bad", "failed"],
    ["outer.inner", "partial"],
    ["outer.after", "success"],
    ["outer", "success"],
  ]);
  assert.equal(result.status, "partial");
});

test("a when guard on the block decides first", async () => {
  const { result } = await run([{ id: "blk", action: "optional", when: "false", steps: [BOOM] }]);
  assert.equal(result.status, "success");
  assert.deepEqual(statuses(result), [["blk", "skipped"]]);
});

test("cancelling during a block stops the run instead of being tolerated", async () => {
  // The block absorbs `StepFailed` only. A cancellation is someone's will, not a reading that did
  // not arrive: catching `AetheriusError` here instead would turn it into a partial success — the
  // run would end `partial`, and an application would show a screen for a user who had left.
  //
  // The real vector driver runs this one: `wait` has to actually wait for a cancellation to have
  // something to interrupt.
  const controller = new AbortController();
  const sink = new CollectingSink();
  const pending = new RunEngine().run(
    {
      aetherius: "1.0",
      name: "optional.cancel",
      act: "vector",
      steps: [
        {
          action: "optional",
          steps: [
            { id: "nap", action: "wait", ms: 5000 },
            { id: "never", action: "set", value: 1 },
          ],
        },
        { id: "after", action: "set", value: 1 },
      ],
    },
    { signal: controller.signal, sinks: [sink] },
  );
  setTimeout(() => controller.abort(), 5);
  const result = await pending;

  assert.equal(result.status, "failed");
  assert.ok(result.cause instanceof RunCancelledError, `unexpected cause: ${result.cause}`);
  // Nothing after the cancelled step ran, and no step was marked skipped by the block: the
  // cancellation went straight through it.
  assert.deepEqual(
    result.step_results.map((s) => s.status),
    [],
  );
});

test("an optional without steps is refused at validation", async () => {
  await assert.rejects(
    () => run([{ id: "blk", action: "optional" }]),
    (error) =>
      error instanceof BlueprintValidationError && /'steps'/.test(error.message) && /steps\[0\].steps/.test(error.message),
  );
});
