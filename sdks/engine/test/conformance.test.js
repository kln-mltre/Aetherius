/**
 * The embedded engine replays the shared conformance corpus.
 *
 * Its Python twin is tests/conformance/test_corpus.py; `make conformance` runs both. A case whose
 * two expectations differ is a *declared* divergence — the embedded engine runs a strict subset of
 * the capabilities — and conformance/README.md requires the case to say why.
 *
 * A case declaring `requires: "browser"` is **deferred**, not quietly passed: Act II needs a
 * WebView, which lives in `@aetherius/react-native`, and that package's executor replays the whole
 * corpus with the driver registered. `make conformance` runs both, so nothing is left uncovered —
 * and the test below fails if such cases ever disappear from the corpus.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { describeFailure, expectationFor, loadCases, mismatches, runCase } from "./harness.mjs";

const cases = loadCases();

test("the corpus is not empty", () => {
  // A runner that silently finds nothing is the one failure mode a green suite cannot show.
  assert.ok(cases.length > 0, "no conformance case found under conformance/cases/");
});

test("the corpus still exercises Act II somewhere", () => {
  assert.ok(
    cases.some((kase) => kase.requires === "browser"),
    "no case requires a browser; the Act II half of the corpus has gone missing",
  );
});

for (const kase of cases) {
  if (kase.requires === "browser") {
    test(`conformance: ${kase.name} (replayed by @aetherius/react-native)`, { skip: true }, () => {});
  } else {
    test(`conformance: ${kase.name}`, async () => {
      const actual = await runCase(kase);
      const problems = mismatches(expectationFor(kase), actual);
      assert.deepEqual(problems, [], describeFailure(kase, actual, problems));
    });
  }

  test(`conformance: ${kase.name} declares both engines`, () => {
    // A case expecting only one engine would quietly stop guarding the other.
    assert.deepEqual(Object.keys(kase.data.expect).sort(), ["embedded", "python"]);
  });
}
