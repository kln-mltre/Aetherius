/**
 * Semantic validation: the three rejection motifs, and the walk into flow branches.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { BlueprintValidationError } from "../dist/errors.js";
import { validateForAct } from "../dist/blueprint/validator.js";

const blueprint = (act, steps) => ({ aetherius: "1.0", name: "demo", act, steps });

function rejectedMessage(document) {
  try {
    validateForAct(document);
  } catch (error) {
    assert.ok(error instanceof BlueprintValidationError, `unexpected error: ${error}`);
    return error.message;
  }
  return assert.fail("expected the Blueprint to be rejected");
}

test("a portable Blueprint is accepted", () => {
  validateForAct(blueprint("continuum", [{ action: "navigate", url: "https://example.test" }]));
  validateForAct(blueprint("vector", [{ action: "http.request", url: "https://example.test" }]));
});

test("wrong act: the message names the act to escalate to", () => {
  const message = rejectedMessage(blueprint("vector", [{ action: "click", selector: "#go" }]));
  assert.match(message, /not supported by act='vector'/);
  assert.match(message, /requires act='continuum' or higher/);
  assert.doesNotMatch(message, /embedded engine/);
});

test("not portable: the message says the act is right and the platform is not", () => {
  const message = rejectedMessage(blueprint("continuum", [{ action: "upload", file: "a.png" }]));
  assert.match(message, /supported by act='continuum' but not by the embedded engine/);
  assert.match(message, /file chooser/);
  assert.doesNotMatch(message, /requires act=/);
});

test("notify is rejected as not portable, not as an unknown action", () => {
  const message = rejectedMessage(blueprint("vector", [{ action: "notify", channel: {} }]));
  assert.match(message, /not by the embedded engine/);
  assert.match(message, /notifications/);
});

test("an act the engine does not run is rejected before anything else", () => {
  const message = rejectedMessage(blueprint("oracle", [{ action: "navigate", url: "x" }]));
  assert.match(message, /Act 'oracle' is not supported by the embedded engine/);
  assert.match(message, /Embedded acts: vector, continuum/);
});

test("an action introduced by a non-embedded act points at the Python engine", () => {
  const message = rejectedMessage(blueprint("continuum", [{ action: "read", vision: "the price" }]));
  assert.match(message, /requires act='oracle', which stays on the Python engine/);
});

test("an unknown action is reported as unknown", () => {
  const message = rejectedMessage(blueprint("vector", [{ action: "teleport" }]));
  assert.match(message, /is not a known action/);
});

test("a goal-only Blueprint is rejected: Phantom stays on the Python engine", () => {
  const message = rejectedMessage({
    aetherius: "1.0",
    name: "demo",
    act: "vector",
    goal: "do the thing",
    steps: [],
  });
  assert.match(message, /goal-only Blueprint/);
  assert.match(message, /act='phantom'/);
});

test("the walk descends into then/else and reports a readable path", () => {
  const message = rejectedMessage(
    blueprint("vector", [
      { action: "set", values: {} },
      { action: "emit", event: "A" },
      { action: "emit", event: "B" },
      {
        action: "if",
        condition: "{{ true }}",
        then: [{ action: "emit", event: "C" }, { action: "screenshot" }],
        else: [{ action: "emit", event: "D" }],
      },
    ]),
  );
  assert.match(message, /at steps\[3\]\.then\[1\]/);
});

test("the walk descends into for_each and repeat", () => {
  const message = rejectedMessage(
    blueprint("vector", [
      { action: "for_each", items: "{{ inputs.rows }}", as: "row", steps: [{ action: "drag" }] },
    ]),
  );
  assert.match(message, /at steps\[0\]\.steps\[0\]/);
});

test("a nested step inherits the enclosing step's act override", () => {
  // `click` is out of reach for the Blueprint act, but the enclosing `if` escalates to continuum
  // and the branch inherits it — same rule as the Python validator.
  validateForAct(
    blueprint("vector", [
      {
        action: "if",
        act: "continuum",
        condition: "{{ true }}",
        then: [{ action: "click", selector: "#go" }],
      },
    ]),
  );
});

test("a per-step act the engine does not run is rejected", () => {
  const message = rejectedMessage(
    blueprint("continuum", [{ id: "look", action: "read", act: "oracle", vision: "the price" }]),
  );
  assert.match(message, /Act 'oracle' is not supported by the embedded engine/);
  assert.match(message, /step 'look'/);
});
