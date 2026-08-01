/**
 * The embedded engine replays the shared conformance corpus.
 *
 * Its Python twin is tests/conformance/test_corpus.py; `make conformance` runs both. A case whose
 * two expectations differ is a *declared* divergence — the embedded engine runs a strict subset of
 * the capabilities — and conformance/README.md requires the case to say why.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  describeFailure,
  expectationFor,
  loadCases,
  mismatches,
  runCase,
} from "./harness.mjs";

const cases = loadCases();

test("the corpus is not empty", () => {
  // A runner that silently finds nothing is the one failure mode a green suite cannot show.
  assert.ok(cases.length > 0, "no conformance case found under conformance/cases/");
});

for (const kase of cases) {
  test(`conformance: ${kase.name}`, () => {
    const actual = runCase(kase);
    const problems = mismatches(expectationFor(kase), actual);
    assert.deepEqual(problems, [], describeFailure(kase, actual, problems));
  });

  test(`conformance: ${kase.name} declares both engines`, () => {
    // A case expecting only one engine would quietly stop guarding the other.
    assert.deepEqual(Object.keys(kase.data.expect).sort(), ["embedded", "python"]);
  });
}
