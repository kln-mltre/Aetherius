/**
 * The embedded engine replays the conformance corpus **with Act II wired in**.
 *
 * The engine's own executor cannot: a `continuum` Blueprint needs a WebView, and a WebView needs a
 * platform. So the corpus is replayed here too, with the Continuum driver registered on a
 * jsdom-backed host — the same comparison code (`harness.mjs` is imported, not copied), the same
 * cases, the same expectations.
 *
 * Replaying the *whole* corpus rather than only the browser cases is deliberate: the two executors
 * then overlap instead of partitioning, and no case can fall between them because someone
 * mislabelled it. The overlap costs a second or two; a hole in the corpus would cost a silent
 * divergence between the two engines.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  describeFailure,
  expectationFor,
  loadCases,
  mismatches,
  runCase,
} from "../../engine/test/harness.mjs";

import { registerContinuum } from "../dist/registry.js";
import { createDomHost } from "./dom-host.mjs";

// A fresh view per run, as a device would give: the driver disposes it at teardown, which drops the
// document and — for an isolated session — the store that came with it.
registerContinuum(() => createDomHost().host);

const cases = loadCases();
const browserCases = cases.filter((kase) => kase.requires === "browser");

test("the corpus is not empty", () => {
  assert.ok(cases.length > 0, "no conformance case found under conformance/cases/");
});

test("this executor is the one that covers the browser cases", () => {
  // The engine's executor defers them. If none reached here, both executors would be skipping the
  // whole Act II comparison and both suites would still be green.
  assert.ok(browserCases.length > 0, "no case requires a browser; Act II is no longer compared");
});

for (const kase of cases) {
  test(`conformance: ${kase.name}`, async () => {
    const actual = await runCase(kase);
    const problems = mismatches(expectationFor(kase), actual);
    assert.deepEqual(problems, [], describeFailure(kase, actual, problems));
  });
}
