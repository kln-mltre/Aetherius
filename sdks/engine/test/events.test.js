/**
 * The event bus: order preserved, and a faulty sink never breaks the stream.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { CollectingSink, SimpleEventBus, formatEvent } from "../dist/events/index.js";

const event = (type, extra = {}) => ({ run_id: "r", ts: "2026-08-01T10:00:00Z", type, ...extra });

test("every registered sink receives every event, in order", () => {
  const bus = new SimpleEventBus(() => {});
  const first = new CollectingSink();
  const second = new CollectingSink();
  bus.register(first);
  bus.register(second);

  bus.emit(event("progress", { message: "run started" }));
  bus.emit(event("done", { data: { status: "success" } }));

  assert.deepEqual(
    first.events.map((e) => e.type),
    ["progress", "done"],
  );
  assert.deepEqual(
    second.events.map((e) => e.type),
    ["progress", "done"],
  );
});

test("a sink that throws is logged and swallowed; the next sinks still receive the event", () => {
  const logged = [];
  const bus = new SimpleEventBus((message, error) => logged.push({ message, error }));
  const survivor = new CollectingSink();
  bus.register({
    onEvent() {
      throw new Error("consumer bug");
    },
  });
  bus.register(survivor);

  bus.emit(event("progress"));

  assert.equal(survivor.events.length, 1);
  assert.equal(logged.length, 1);
  assert.equal(logged[0].error.message, "consumer bug");
});

test("formatEvent renders one readable line", () => {
  assert.equal(formatEvent(event("step_started", { step_id: "login" })), "[step_started] step=login");
  assert.equal(formatEvent(event("progress", { message: "hi" })), "[progress] hi");
});
