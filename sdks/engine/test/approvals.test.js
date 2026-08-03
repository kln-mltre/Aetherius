/**
 * The human-in-the-loop rendezvous, and the attended path of `confirm`.
 *
 * What is pinned here is not "a promise resolves": it is the four decisions the milestone had to
 * make, each of which would be a silent hazard on a phone if it went the other way — deny by
 * default, first writer wins, a decision arriving after expiry is ignored, and a foreign token
 * resolves nothing.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { ApprovalRegistry, createApprovalRequest } from "../dist/runtime/approvals.js";
import { CollectingSink } from "../dist/events/index.js";
import { RunEngine } from "../dist/runtime/engine.js";

const request = (options = {}) =>
  createApprovalRequest("run-1", "Publish?", { timeoutMs: 50, ...options });

async function run(steps, options = {}) {
  const sink = new CollectingSink();
  const result = await new RunEngine().run(
    { aetherius: "1.0", name: "approvals.demo", act: "vector", steps },
    { ...options, sinks: [sink] },
  );
  return { result, events: sink.events };
}

const outputs = (result, id) => result.step_results.find((s) => s.step_id === id).outputs;

test("a rendezvous resolves with the decision it was given", async () => {
  const registry = new ApprovalRegistry();
  const pending = registry.open(request({ timeoutMs: 5000 }));
  const waiting = pending.wait();

  assert.equal(registry.resolve("run-1", pending.request.token, { approved: true, decidedBy: "modal" }), true);
  assert.deepEqual(await waiting, { approved: true, decidedBy: "modal" });
});

test("a rendezvous nobody answers expires, and expiry is null rather than a decision", async () => {
  const pending = new ApprovalRegistry().open(request({ timeoutMs: 20 }));
  assert.equal(await pending.wait(), null);
});

test("the first writer wins: a second decision is a no-op, never a double apply", async () => {
  const registry = new ApprovalRegistry();
  const pending = registry.open(request({ timeoutMs: 5000 }));
  const waiting = pending.wait();

  assert.equal(pending.resolve({ approved: false, decidedBy: "modal" }), true);
  assert.equal(pending.resolve({ approved: true, decidedBy: "modal" }), false);
  assert.deepEqual(await waiting, { approved: false, decidedBy: "modal" });
});

test("a decision arriving after expiry is ignored", async () => {
  // The case an application hits for real: a phone in the background freezes its timers, the modal
  // is tapped on resume, and the run has already moved on. Answering then would apply a decision to
  // a step that is finished.
  const pending = new ApprovalRegistry().open(request({ timeoutMs: 10 }));
  assert.equal(await pending.wait(), null);
  assert.equal(pending.expired, true);
  assert.equal(pending.resolve({ approved: true, decidedBy: "modal" }), false);
});

test("a foreign token resolves nothing, and neither does an unknown run", async () => {
  const registry = new ApprovalRegistry();
  const pending = registry.open(request({ timeoutMs: 5000 }));

  assert.equal(registry.resolve("run-1", "not-the-token", { approved: true }), false);
  assert.equal(registry.resolve("other-run", pending.request.token, { approved: true }), false);
  assert.equal(await pending.wait(), null);
});

test("closing a request forgets it, so a late decision finds nothing", async () => {
  const registry = new ApprovalRegistry();
  const pending = registry.open(request({ timeoutMs: 5000 }));
  registry.close(pending.request);

  assert.equal(registry.request("run-1"), undefined);
  assert.equal(registry.resolve("run-1", pending.request.token, { approved: true }), false);
});

test("an attended confirm parks the run and resumes on the decision", async () => {
  const registry = new ApprovalRegistry();
  const started = Date.now();
  const pending = run(
    [
      { id: "ask", action: "confirm", message: "Publish?", title: "Post", timeout_ms: 5000 },
      { id: "publish", action: "set", when: "{{ steps.ask.approved }}", value: "sent" },
    ],
    { runId: "run-parked", approvals: registry },
  );

  // The step really waits: the decision is what moves it on, not a timeout that happened to be
  // short. Polling because the run parks asynchronously.
  let request_;
  while ((request_ = registry.request("run-parked")) === undefined) await sleep(5);
  await sleep(30);
  registry.resolve("run-parked", request_.token, { approved: true, value: 42, decidedBy: "modal" });

  const { result, events } = await pending;
  assert.ok(Date.now() - started >= 30, "the run did not actually park");
  assert.equal(result.status, "success");
  assert.deepEqual(outputs(result, "ask"), {
    approved: true,
    decision: "approved",
    value: 42,
    decided_by: "modal",
  });
  assert.equal(outputs(result, "publish").value, "sent");

  const kinds = events.map((event) => event.type);
  assert.ok(kinds.includes("input_requested"), "no input_requested event");
  assert.ok(kinds.includes("input_provided"), "no input_provided event");
  // The status never changes while parked: a parked run is a running run (docs/human-in-the-loop.md).
  assert.equal(events.filter((event) => event.type === "done").length, 1);
});

test("the request event carries the token, the title and the deadline", async () => {
  const registry = new ApprovalRegistry();
  const pending = run(
    [{ id: "ask", action: "confirm", message: "Publish {{ 'now' }}?", title: "Post", timeout_ms: 3000 }],
    { runId: "run-data", approvals: registry },
  );

  let opened;
  while ((opened = registry.request("run-data")) === undefined) await sleep(5);
  registry.resolve("run-data", opened.token, { approved: false, decidedBy: "modal" });

  const { events } = await pending;
  const asked = events.find((event) => event.type === "input_requested");
  assert.equal(asked.step_id, "ask");
  assert.equal(asked.level, "warning");
  // Rendered, like Python's: the human reads the question, not the template.
  assert.equal(asked.message, "Publish now?");
  assert.deepEqual(asked.data, { token: opened.token, title: "Post", timeout_ms: 3000 });

  const answered = events.find((event) => event.type === "input_provided");
  assert.deepEqual(answered.data, { token: opened.token, approved: false, decided_by: "modal" });
});

test("an attended confirm nobody answers falls back on on_timeout, denying by default", async () => {
  const { result, events } = await run(
    [{ id: "ask", action: "confirm", message: "Publish?", timeout_ms: 30 }],
    { approvals: new ApprovalRegistry() },
  );
  assert.equal(result.status, "success");
  assert.equal(outputs(result, "ask").approved, false);
  assert.equal(outputs(result, "ask").decided_by, "timeout");
  // `timeout` is a decider like any other in the trace, exactly as Python records it.
  assert.equal(events.find((event) => event.type === "input_provided").data.decided_by, "timeout");
});

test("a gateway is asked nothing when the Blueprint has no confirm", async () => {
  const registry = new ApprovalRegistry();
  const { result } = await run([{ id: "one", action: "set", value: 1 }], { approvals: registry });
  assert.equal(result.status, "success");
  assert.equal(registry.request("run-1"), undefined);
});

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
