/**
 * The runtime: step order, the `when` guard, the flow actions, and how a run fails.
 *
 * Everything here is observable behaviour the Python engine already has, so the assertions are
 * written against the *stream* — step results and events — rather than against internals. A driver
 * that records its calls stands in for an Act: none is needed to prove the pipeline.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { ActionError, RunError, TemplateError } from "../dist/errors.js";
import { CollectingSink } from "../dist/events/index.js";
import { RunEngine, registerDriver } from "../dist/index.js";

/** An Act made of one recording driver, registered under a spare act name. */
function recorder({ fail } = {}) {
  const calls = [];
  const driver = {
    act: "vector",
    setup: async () => calls.push("setup"),
    teardown: async () => calls.push("teardown"),
    runStep: async (step, _ctx, _bus, render) => {
      calls.push(step.id ?? step.action);
      if (fail !== undefined && step.id === fail) throw new ActionError(`boom: ${step.id}`);
      return { echo: render(step["echo"] ?? null) };
    },
  };
  return { calls, driver };
}

/** Replace the vector driver for the duration of one run, then put the real one back. */
async function runWith(driver, blueprint, options = {}) {
  const sink = new CollectingSink();
  const { VectorDriver } = await import("../dist/acts/vector/driver.js");
  registerDriver("vector", () => driver);
  try {
    const result = await new RunEngine().run(blueprint, { ...options, sinks: [sink] });
    return { result, events: sink.events };
  } finally {
    registerDriver("vector", (host) => new VectorDriver(host));
  }
}

const blueprint = (steps, extra = {}) => ({
  aetherius: "1.0",
  name: "runtime.demo",
  act: "vector",
  steps,
  ...extra,
});

const trace = (events) => events.map((e) => `${e.type}(${e.step_id ?? "-"})`);

test("steps run in order, each producing one result and a started/finished pair", async () => {
  const { calls, driver } = recorder();
  const { result, events } = await runWith(
    driver,
    blueprint([
      { id: "first", action: "set", value: "a" },
      { id: "second", action: "set", value: "b" },
    ]),
  );

  assert.deepEqual(calls, ["setup", "first", "second", "teardown"]);
  assert.equal(result.status, "success");
  assert.deepEqual(
    result.step_results.map((s) => [s.step_id, s.status]),
    [
      ["first", "success"],
      ["second", "success"],
    ],
  );
  assert.deepEqual(trace(events), [
    "progress(-)",
    "step_started(first)",
    "step_finished(first)",
    "step_started(second)",
    "step_finished(second)",
    "done(-)",
  ]);
});

test("a falsy `when` skips the step and publishes the raw expression, never its value", async () => {
  const { calls, driver } = recorder();
  const { result, events } = await runWith(
    driver,
    blueprint([{ id: "guarded", action: "set", when: "{{ secrets.token }}", value: "x" }]),
    { secrets: { token: "s3cret" } },
  );

  assert.deepEqual(calls, ["setup", "teardown"], "the driver never saw the step");
  assert.equal(result.step_results[0].status, "skipped");
  const skipped = events.find((e) => e.type === "step_skipped");
  assert.equal(skipped.data.when, "{{ secrets.token }}");
  assert.equal(JSON.stringify(events).includes("s3cret"), false);
});

test("a truthy `when` runs the step", async () => {
  const { calls, driver } = recorder();
  await runWith(driver, blueprint([{ id: "guarded", action: "set", when: "{{ 'yes' }}" }]));
  assert.deepEqual(calls, ["setup", "guarded", "teardown"]);
});

test("nested flow steps carry their full path; root steps keep their bare id", async () => {
  const { driver } = recorder();
  const { result, events } = await runWith(
    driver,
    blueprint([
      {
        id: "branch",
        action: "if",
        condition: "{{ true }}",
        then: [
          {
            id: "loop",
            action: "for_each",
            items: "{{ [10, 20] }}",
            as: "n",
            steps: [{ id: "inner", action: "set", echo: "{{ n }}" }],
          },
        ],
      },
    ]),
  );

  assert.deepEqual(
    result.step_results.map((s) => s.step_id),
    [
      "branch.loop[0].inner",
      "branch.loop[1].inner",
      "branch.loop",
      "branch",
    ],
  );
  assert.deepEqual(
    result.step_results.filter((s) => s.step_id.endsWith("inner")).map((s) => s.outputs.echo),
    [10, 20],
  );
  assert.deepEqual(trace(events).slice(1, -1), [
    "step_started(branch)",
    "step_started(branch.loop)",
    "step_started(branch.loop[0].inner)",
    "step_finished(branch.loop[0].inner)",
    "step_started(branch.loop[1].inner)",
    "step_finished(branch.loop[1].inner)",
    "step_finished(branch.loop)",
    "step_finished(branch)",
  ]);
});

test("the loop variable is restored on the way out, so nested loops compose", async () => {
  const { driver } = recorder();
  const { result } = await runWith(
    driver,
    blueprint([
      {
        id: "outer",
        action: "for_each",
        items: "{{ ['a', 'b'] }}",
        as: "item",
        steps: [
          {
            id: "inner",
            action: "for_each",
            items: "{{ [1] }}",
            as: "item",
            steps: [{ id: "deep", action: "set", echo: "{{ item }}" }],
          },
          { id: "after", action: "set", echo: "{{ item }}" },
        ],
      },
    ]),
  );

  const echoed = (suffix) =>
    result.step_results.filter((s) => s.step_id.endsWith(suffix)).map((s) => s.outputs.echo);
  assert.deepEqual(echoed("deep"), [1, 1]);
  assert.deepEqual(echoed("after"), ["a", "b"], "the outer variable came back after the inner loop");
});

test("a for_each over zero items runs nothing and still succeeds", async () => {
  const { calls, driver } = recorder();
  const { result } = await runWith(
    driver,
    blueprint([
      {
        id: "loop",
        action: "for_each",
        items: "{{ [] }}",
        steps: [{ id: "never", action: "set" }],
      },
    ]),
  );

  assert.deepEqual(calls, ["setup", "teardown"]);
  assert.equal(result.status, "success");
  assert.deepEqual(result.step_results.map((s) => s.step_id), ["loop"]);
  assert.equal(result.step_results[0].outputs.iterations, 0);
});

test("repeat runs its steps `times` times, sequentially", async () => {
  const { calls, driver } = recorder();
  await runWith(
    driver,
    blueprint([
      { id: "loop", action: "repeat", times: "{{ 3 }}", steps: [{ id: "tick", action: "set" }] },
    ]),
  );
  assert.deepEqual(calls, ["setup", "tick", "tick", "tick", "teardown"]);
});

test("an if without a matching else branch reports no branch and runs nothing", async () => {
  const { calls, driver } = recorder();
  const { result } = await runWith(
    driver,
    blueprint([
      { id: "branch", action: "if", condition: "{{ false }}", then: [{ id: "no", action: "set" }] },
    ]),
  );
  assert.deepEqual(calls, ["setup", "teardown"]);
  assert.equal(result.step_results[0].outputs.branch, null);
});

test("a failing step aborts the run and is reported without a stack", async () => {
  const { calls, driver } = recorder({ fail: "second" });
  const { result, events } = await runWith(
    driver,
    blueprint([
      { id: "first", action: "set" },
      { id: "second", action: "set" },
      { id: "third", action: "set" },
    ]),
  );

  assert.deepEqual(calls, ["setup", "first", "second", "teardown"]);
  assert.equal(result.status, "failed");
  assert.equal(result.error, "boom: second");
  assert.deepEqual(result.outputs, {}, "a failed run publishes no outputs");
  assert.deepEqual(
    result.step_results.map((s) => s.status),
    ["success", "failed"],
  );
  assert.deepEqual(trace(events).slice(-2), ["error(second)", "done(-)"]);
});

test("a failure inside a branch marks the enclosing flow step, without a duplicate event", async () => {
  const { driver } = recorder({ fail: "inner" });
  const { result, events } = await runWith(
    driver,
    blueprint([
      {
        id: "branch",
        action: "if",
        condition: "{{ true }}",
        then: [{ id: "inner", action: "set" }],
      },
    ]),
  );

  assert.equal(result.status, "failed");
  assert.deepEqual(
    result.step_results.map((s) => [s.step_id, s.status]),
    [
      ["branch.inner", "failed"],
      ["branch", "failed"],
    ],
  );
  assert.deepEqual(
    events.filter((e) => e.type === "error").map((e) => e.step_id),
    ["branch.inner"],
  );
});

test("an error that is not an AetheriusError is wrapped in a RunError and rethrown", async () => {
  const driver = {
    act: "vector",
    setup: async () => {},
    teardown: async () => {},
    runStep: async () => {
      throw new TypeError("engine bug");
    },
  };
  await assert.rejects(
    () => runWith(driver, blueprint([{ id: "boom", action: "set" }])),
    (error) => error instanceof RunError && /engine bug/.test(error.message),
  );
});

test("outputs render after the steps, and an undefined variable there raises", async () => {
  const { driver } = recorder();
  const { result } = await runWith(
    driver,
    blueprint([{ id: "one", action: "set", echo: "{{ 42 }}" }], {
      outputs: { echoed: "{{ steps.one.echo }}" },
    }),
  );
  assert.deepEqual(result.outputs, { echoed: 42 });

  await assert.rejects(
    () =>
      runWith(driver, blueprint([{ id: "one", action: "set" }], { outputs: { x: "{{ nope }}" } })),
    TemplateError,
  );
});

test("a missing required input is refused before anything runs", async () => {
  const { calls, driver } = recorder();
  await assert.rejects(
    () =>
      runWith(driver, {
        aetherius: "1.0",
        name: "needs.input",
        act: "vector",
        inputs: { who: { type: "string", required: true } },
        steps: [{ id: "one", action: "set" }],
      }),
    /Missing required input 'who'/,
  );
  assert.deepEqual(calls, [], "inputs are resolved before any Act is started");
});

test("declared inputs fall back to their default; extra caller inputs pass through", async () => {
  const { driver } = recorder();
  const { result } = await runWith(
    driver,
    {
      aetherius: "1.0",
      name: "defaults",
      act: "vector",
      inputs: { limit: { type: "integer", default: 3 } },
      // Leading text on purpose: a string that both starts and ends with an expression is read as
      // one malformed expression, on both engines (docs/embedded.md, known limits).
      steps: [{ id: "one", action: "set", echo: "limit={{ inputs.limit }} extra={{ inputs.extra }}" }],
    },
    { inputs: { extra: "x" } },
  );
  assert.equal(result.step_results[0].outputs.echo, "limit=3 extra=x");
});
