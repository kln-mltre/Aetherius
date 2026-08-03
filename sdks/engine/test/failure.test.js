/**
 * The error model: `describeFailure`.
 *
 * The point of these tests is not coverage of a switch. It is the sentence the milestone exists to
 * make true: **a broken source and a legitimately empty answer must not look the same**. The last
 * two tests are the ones that would catch a regression there; the rest keep each typed family
 * landing on the screen it belongs to.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  ActionError,
  BlueprintValidationError,
  DependencyError,
  ExtractionError,
  NetworkError,
  RetryExhaustedError,
  RunCancelledError,
  RunError,
  StatusAssertionError,
  StepTimeoutError,
  TemplateError,
  TimeoutError,
} from "../dist/errors.js";
import { describeFailure } from "../dist/failure.js";
import { RunEngine } from "../dist/runtime/engine.js";

const kindOf = (error) => describeFailure(error).kind;

test("each typed family reaches the caller as its own kind", () => {
  assert.equal(kindOf(new BlueprintValidationError("x")), "blueprint");
  assert.equal(kindOf(new NetworkError("x")), "unavailable");
  assert.equal(kindOf(new TimeoutError("x")), "unavailable");
  assert.equal(kindOf(new RetryExhaustedError("x")), "unavailable");
  assert.equal(kindOf(new StatusAssertionError("x")), "rejected");
  assert.equal(kindOf(new ExtractionError("x")), "data");
  // `config`, not `data`: an expression that will not render says nothing about the source.
  assert.equal(kindOf(new TemplateError("x")), "config");
  assert.equal(kindOf(new RunCancelledError("x")), "cancelled");
  assert.equal(kindOf(new DependencyError("x")), "unsupported");
  assert.equal(kindOf(new ActionError("x")), "engine");
  assert.equal(kindOf(new RunError("x")), "engine");
  assert.equal(kindOf(new Error("something else")), "engine");
});

test("a named step failure carries its code, which is what an application branches on", () => {
  const failure = describeFailure(new StepTimeoutError("login never settled", "LOGIN_FAILED"));
  assert.equal(failure.kind, "blocked");
  assert.equal(failure.code, "LOGIN_FAILED");
  assert.equal(failure.retryable, false);
});

test("only the failures worth retrying say so", () => {
  assert.equal(describeFailure(new NetworkError("x")).retryable, true);
  assert.equal(describeFailure(new StatusAssertionError("x")).retryable, true);
  assert.equal(describeFailure(new BlueprintValidationError("x")).retryable, false);
  assert.equal(describeFailure(new RunCancelledError("x")).retryable, false);
});

test("an unnamed timeout is a page that did not match, not a named block", () => {
  // The split is the useful one on screen: `fail:LOGIN_FAILED` is something to show the user, an
  // anonymous `wait_for` expiry only means the page is not the one the Blueprint describes.
  const failure = describeFailure(new StepTimeoutError("wait_for timed out for selector '#x'"));
  assert.equal(failure.kind, "data");
  assert.equal(failure.code, undefined);
});

test("a failed run is classified from its cause, not from its message", async () => {
  const result = await new RunEngine().run(
    {
      aetherius: "1.0",
      name: "failure.demo",
      act: "vector",
      steps: [{ id: "get", action: "http.request", url: "https://example.invalid/" }],
    },
    { fetch: async () => { throw new Error("getaddrinfo ENOTFOUND"); } },
  );

  assert.equal(result.status, "failed");
  const failure = describeFailure(result);
  assert.equal(failure.kind, "unavailable");
  assert.equal(failure.error, "NetworkError");
  assert.equal(failure.retryable, true);
});

test("an empty answer is a success, not a failure — the whole point of the model", async () => {
  const result = await new RunEngine().run(
    {
      aetherius: "1.0",
      name: "failure.empty",
      act: "vector",
      steps: [
        {
          id: "get",
          action: "http.request",
          url: "https://example.invalid/items",
          extract: { items: { from: "json", path: "$.items[*]" } },
        },
      ],
      outputs: { items: "{{ steps.get.items }}" },
    },
    { fetch: async () => jsonResponse({ items: [] }) },
  );

  assert.equal(result.status, "success");
  assert.deepEqual(result.outputs, { items: [] });
  // A source that is down and a source with nothing to say produce two different outcomes. A
  // service layer that caught everything and returned `[]` would make them one.
  assert.equal(describeFailure(result), undefined);
});

test("describeFailure ignores what is not a failure", () => {
  assert.equal(describeFailure(undefined), undefined);
  assert.equal(describeFailure(null), undefined);
  assert.equal(describeFailure({ not: "a result" }), undefined);
});

function jsonResponse(body) {
  return {
    status: 200,
    url: "https://example.invalid/items",
    headers: { get: () => null, forEach: () => {} },
    text: async () => JSON.stringify(body),
  };
}
