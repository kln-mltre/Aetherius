/**
 * `confirm` on a phone: one rendezvous, one surface.
 *
 * The gateway is plain TypeScript on purpose — the React modal is an *habillage* over it — so the
 * four decisions that matter can be tested without a rendering engine: approve, reject, expiry
 * denies by default, and a decision tapped after expiry does nothing.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { Aetherius } from "../dist/aetherius.js";
import { ConfirmGateway } from "../dist/confirm/gateway.js";

const blueprint = (steps, extra = {}) => ({
  aetherius: "1.0",
  name: "confirm.demo",
  act: "vector",
  ...extra,
  steps,
});

/**
 * Start a run and wait until it is parked on its `confirm`.
 *
 * Subscribing first is what a mounted `<AetheriusConfirm />` does, and it is what makes the run
 * *attended*: a gateway nobody listens to denies at once, on purpose (see the last two tests).
 */
async function parked(client, gateway, steps, extra) {
  const events = [];
  const watching = gateway.subscribe(() => {});
  const pending = client.run(blueprint(steps, extra), { onEvent: (event) => events.push(event) });
  while (gateway.current() === undefined) await sleep(5);
  return { pending, events, watching };
}

const outputs = (result, id) => result.step_results.find((s) => s.step_id === id).outputs;

test("approving resumes the run and lets the guarded step through", async () => {
  const gateway = new ConfirmGateway();
  const client = new Aetherius({ approvals: gateway });
  const { pending } = await parked(client, gateway, [
    { id: "ask", action: "confirm", message: "Publier ?", timeout_ms: 5000 },
    { id: "publish", action: "set", when: "{{ steps.ask.approved }}", value: "envoye" },
  ]);

  assert.equal(gateway.decide({ approved: true, decidedBy: "modal" }), true);
  const result = await pending;

  assert.equal(result.status, "success");
  assert.equal(outputs(result, "ask").decided_by, "modal");
  assert.equal(outputs(result, "publish").value, "envoye");
});

test("refusing skips the guarded step, and the run is still a success", async () => {
  // Deny-by-default composes: the sensitive step is simply not played, and nothing fails.
  const gateway = new ConfirmGateway();
  const client = new Aetherius({ approvals: gateway });
  const { pending } = await parked(client, gateway, [
    { id: "ask", action: "confirm", message: "Publier ?", timeout_ms: 5000 },
    { id: "publish", action: "set", when: "{{ steps.ask.approved }}", value: "envoye" },
  ]);

  gateway.decide({ approved: false, decidedBy: "modal" });
  const result = await pending;

  assert.equal(result.status, "success");
  assert.equal(result.step_results[1].status, "skipped");
});

test("nobody answering denies, which is the behaviour a backgrounded app gets for free", async () => {
  const gateway = new ConfirmGateway();
  const watching = gateway.subscribe(() => {});
  const client = new Aetherius({ approvals: gateway });
  const result = await client.run(
    blueprint([{ id: "ask", action: "confirm", message: "Publier ?", timeout_ms: 40 }]),
  );
  watching();

  assert.equal(result.status, "success");
  assert.equal(outputs(result, "ask").approved, false);
  assert.equal(outputs(result, "ask").decided_by, "timeout");
  assert.equal(gateway.current(), undefined, "the request outlived the run");
});

test("a decision tapped after expiry does nothing", async () => {
  const gateway = new ConfirmGateway();
  const client = new Aetherius({ approvals: gateway });
  const { pending } = await parked(client, gateway, [
    { id: "ask", action: "confirm", message: "Publier ?", timeout_ms: 40 },
  ]);

  const result = await pending;
  assert.equal(outputs(result, "ask").decided_by, "timeout");
  // The modal has been dismissed by then; a late tap must not resolve a step that is over.
  assert.equal(gateway.decide({ approved: true, decidedBy: "modal" }), false);
});

test("subscribers see the request appear and disappear", async () => {
  const gateway = new ConfirmGateway();
  const client = new Aetherius({ approvals: gateway });
  const seen = [];
  const unsubscribe = gateway.subscribe((request) => seen.push(request?.message));

  const { pending } = await parked(client, gateway, [
    { id: "ask", action: "confirm", message: "Publier ?", title: "Post", timeout_ms: 5000 },
  ]);
  assert.equal(gateway.current().title, "Post");
  gateway.decide({ approved: true, decidedBy: "modal" });
  await pending;
  unsubscribe();

  // Delivered on subscribe, then the request, then its disappearance: enough for a modal to open
  // and close without any state of its own.
  assert.deepEqual(seen, [undefined, "Publier ?", undefined]);
});

test("a subscriber that throws does not break the run", async () => {
  const gateway = new ConfirmGateway();
  gateway.subscribe(() => {
    throw new Error("a buggy screen");
  });
  // Subscribing at all is what makes the run attended; the throw must not change that.
  const client = new Aetherius({ approvals: gateway });
  const result = await client.run(
    blueprint([{ id: "ask", action: "confirm", message: "Publier ?", timeout_ms: 30 }]),
  );
  assert.equal(result.status, "success");
});

test("nobody listening means unattended: the run denies at once instead of parking", async () => {
  // A screen that mounted neither <AetheriusConfirm /> nor useApprovalRequest will never show the
  // question. Parking five minutes in front of it would be a deadlock with no visible cause; a
  // library run on the Python engine behaves exactly this way for the same reason.
  const client = new Aetherius({ approvals: new ConfirmGateway() });
  const started = Date.now();
  const result = await client.run(
    blueprint([{ id: "ask", action: "confirm", message: "Publier ?", timeout_ms: 300000 }]),
  );
  assert.equal(outputs(result, "ask").approved, false);
  assert.ok(Date.now() - started < 1000, "the run parked with nobody to answer");
});

test("a mounted surface makes the same run attended", async () => {
  // The mirror of the previous test: the only thing that changed is that someone subscribed.
  const gateway = new ConfirmGateway();
  const unsubscribe = gateway.subscribe(() => {});
  const client = new Aetherius({ approvals: gateway });
  const started = Date.now();
  const result = await client.run(
    blueprint([{ id: "ask", action: "confirm", message: "Publier ?", timeout_ms: 200 }]),
  );
  unsubscribe();
  assert.ok(Date.now() - started >= 150, "the run did not park");
  assert.equal(outputs(result, "ask").decided_by, "timeout");
});

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
