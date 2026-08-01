/**
 * Loading a Blueprint: two steps, two errors. Imports the compiled output (built by `npm test`).
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { BlueprintLoadError, BlueprintSchemaError } from "../dist/errors.js";
import { parseBlueprint, validateBlueprintData } from "../dist/blueprint/loader.js";

const MINIMAL = {
  aetherius: "1.0",
  name: "demo.minimal",
  act: "vector",
  steps: [{ action: "emit", event: "READY" }],
};

test("a valid document is returned typed", () => {
  const blueprint = parseBlueprint(JSON.stringify(MINIMAL), "minimal.json");
  assert.equal(blueprint.name, "demo.minimal");
  assert.equal(blueprint.steps.length, 1);
});

test("malformed JSON raises BlueprintLoadError, not a schema error", () => {
  assert.throws(() => parseBlueprint("{ not json", "broken.json"), (error) => {
    assert.ok(error instanceof BlueprintLoadError);
    assert.match(error.message, /broken\.json/);
    return true;
  });
});

test("a schema violation names the offending path", () => {
  assert.throws(
    () => validateBlueprintData({ ...MINIMAL, act: "wandering" }, "bad-act.json"),
    (error) => {
      assert.ok(error instanceof BlueprintSchemaError);
      assert.match(error.message, /\/act/);
      assert.match(error.message, /bad-act\.json/);
      return true;
    },
  );
});

test("an unknown top-level key is rejected (additionalProperties: false)", () => {
  assert.throws(
    () => validateBlueprintData({ ...MINIMAL, whatever: 1 }),
    BlueprintSchemaError,
  );
});

test("empty steps with no goal is a model error, as pydantic reports it", () => {
  // The schema's anyOf is satisfied by the mere presence of `steps`; the Python model is what
  // rejects an empty one. Both engines must agree, so the loader reproduces the rule.
  assert.throws(() => validateBlueprintData({ ...MINIMAL, steps: [] }), (error) => {
    assert.ok(error instanceof BlueprintSchemaError);
    assert.match(error.message, /'steps' or 'goal'/);
    return true;
  });
});

test("a goal-only Blueprint passes the schema stage", () => {
  const blueprint = validateBlueprintData({
    aetherius: "1.0",
    name: "demo.goal",
    act: "phantom",
    goal: "find the cheapest book",
  });
  assert.equal(blueprint.goal, "find the cheapest book");
});

test("step parameters beyond the declared ones are passed through", () => {
  const blueprint = validateBlueprintData({
    ...MINIMAL,
    steps: [{ id: "get", action: "http.request", url: "https://example.test", method: "GET" }],
  });
  assert.equal(blueprint.steps[0].url, "https://example.test");
});
