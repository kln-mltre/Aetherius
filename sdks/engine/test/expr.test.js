/**
 * The expression evaluator: precedence, StrictUndefined, filters, and the two truthiness rules.
 *
 * The precedence cases are not decoration. `not x | first` and `x | length > 0` both appear in
 * shipped Blueprints, and both change meaning if the filter level moves.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { TemplateError } from "../dist/errors.js";
import {
  evaluateExpression,
  isTruthy,
  isUndefined,
  pyTruth,
  pythonStr,
} from "../dist/expr/index.js";

const run = (source, ctx = {}) => evaluateExpression(source, ctx);

function failure(source, ctx = {}) {
  try {
    run(source, ctx);
  } catch (error) {
    assert.ok(error instanceof TemplateError, `unexpected error: ${error}`);
    return error.message;
  }
  return assert.fail(`expected ${source} to raise`);
}

// ── Access ───────────────────────────────────────────────────────────────────

test("dotted access, indexing and literals", () => {
  const ctx = { steps: { fetch: { users: [{ name: "Ada" }, { name: "Alan" }] } } };
  assert.equal(run("steps.fetch.users[0].name", ctx), "Ada");
  assert.equal(run("steps.fetch.users[-1].name", ctx), "Alan");
  assert.equal(run("steps['fetch']['users'][1]['name']", ctx), "Alan");
  assert.equal(run("'text'"), "text");
  assert.equal(run("12"), 12);
  assert.equal(run("true"), true);
  assert.equal(run("True"), true);
  assert.equal(run("None"), null);
});

// ── Precedence ───────────────────────────────────────────────────────────────

test("a filter binds tighter than 'not'", () => {
  // `not (values | first)`, not `(not values) | first`.
  assert.equal(run("not values | first", { values: [false] }), true);
  assert.equal(run("not values | first", { values: [true] }), false);
});

test("a filter binds tighter than a comparison", () => {
  assert.equal(run("users | length > 0", { users: [1, 2] }), true);
  assert.equal(run("users | length > 0", { users: [] }), false);
});

test("arithmetic and boolean precedence follow Python", () => {
  assert.equal(run("1 + 2 * 3"), 7);
  assert.equal(run("(1 + 2) * 3"), 9);
  assert.equal(run("3 // 2"), 1);
  // Python's modulo takes the sign of the divisor; JavaScript's would answer -1.
  assert.equal(run("-7 % 3"), 2);
  assert.equal(run("true or false and false"), true);
});

test("chained comparisons behave as in Python", () => {
  assert.equal(run("0 < x < 10", { x: 5 }), true);
  assert.equal(run("0 < x < 10", { x: 50 }), false);
});

// ── Operators ────────────────────────────────────────────────────────────────

test("comparisons are structural, and booleans compare as numbers", () => {
  assert.equal(run("[1, 2] == [1, 2]"), true);
  assert.equal(run("{'a': 1} == {'a': 1}"), true);
  assert.equal(run("1 == true"), true);
  assert.equal(run("'1' == 1"), false);
});

test("'in' covers strings, lists and objects", () => {
  assert.equal(run("'In stock' in text", { text: "In stock (22 available)" }), true);
  assert.equal(run("2 in values", { values: [1, 2] }), true);
  assert.equal(run("'a' not in mapping", { mapping: { b: 1 } }), true);
});

test("and/or return an operand, as Python does", () => {
  assert.equal(run("'' or 'fallback'"), "fallback");
  assert.equal(run("'set' and 'second'"), "second");
});

test("the inline conditional is lazy", () => {
  const ctx = { steps: {} };
  assert.equal(run("steps.publish.post_id if steps.publish is defined else None", ctx), null);
  const present = { steps: { publish: { post_id: 42 } } };
  assert.equal(run("steps.publish.post_id if steps.publish is defined else None", present), 42);
});

test("'is none' answers identity in both dialects", () => {
  assert.equal(run("value is none", { value: null }), true);
  assert.equal(run("value is None", { value: 0 }), false);
  assert.equal(run("value is not None", { value: 0 }), true);
});

// ── StrictUndefined ──────────────────────────────────────────────────────────

test("an absent variable is undefined until something uses it", () => {
  // Producing the marker is silent — `is defined` and the `else` branch of a conditional both
  // need to observe a missing value. Rendering it is the use that raises (see template.test.js).
  assert.ok(isUndefined(run("missing")));
  assert.ok(isUndefined(run("steps.x.missing", { steps: { x: {} } })));
});

test("using an undefined value raises, naming it", () => {
  assert.match(failure("missing | upper"), /Undefined variable in expression: 'missing'/);
  assert.match(failure("steps.x.missing == 1", { steps: { x: {} } }), /'steps\.x\.missing'/);
  // Walking *through* an undefined raises at once, as Jinja does.
  assert.match(failure("nope.deep"), /'nope'/);
});

test("an absent variable is observable without raising", () => {
  assert.equal(run("missing is defined"), false);
  assert.equal(run("missing is not defined"), true);
  assert.equal(run("missing | default('fallback')"), "fallback");
});

test("'default' honours Jinja's boolean mode", () => {
  // Without the second argument only an *undefined* value takes the fallback. With it, any falsy
  // one does — which is how a Blueprint turns a nullable field into an empty string. Missing it
  // kept the `null`: a different value, with the same run status.
  assert.equal(run("nothing | default('x', true)", { nothing: null }), "x");
  assert.equal(run("nothing | default('x')", { nothing: null }), null);
  assert.equal(run("zero | default(9, true)", { zero: 0 }), 9);
  assert.equal(run("zero | default(9)", { zero: 0 }), 0);
  assert.equal(run("value | default('x', true)", { value: "ok" }), "ok");
});

test("'first' on an empty sequence yields undefined, not null", () => {
  assert.ok(isUndefined(run("values | first", { values: [] })));
  assert.match(failure("values | first | upper", { values: [] }), /sequence was empty/);
});

// ── Filters ──────────────────────────────────────────────────────────────────

test("the date filters work on ISO dates", () => {
  assert.equal(run("d | add_days(7)", { d: "2026-09-07" }), "2026-09-14");
  assert.equal(run("d | sub_days(1)", { d: "2026-03-01" }), "2026-02-28");
  assert.equal(run("d | format_date('%d/%m/%Y')", { d: "2026-09-07" }), "07/09/2026");
  assert.equal(run("d | format_date('%A %B %j')", { d: "2026-09-07" }), "Monday September 250");
});

test("a date outside YYYY-MM-DD fails loudly", () => {
  assert.match(failure("d | add_days(1)", { d: "20260907" }), /cannot parse date '20260907'/);
  assert.match(failure("d | add_days(1)", { d: "2026-02-30" }), /cannot parse date/);
  assert.match(
    failure("d | format_date('%Q')", { d: "2026-09-07" }),
    /unsupported strftime directive '%Q'/,
  );
});

test("the built-in filters reproduce Jinja's quirks", () => {
  assert.equal(run("values | length", { values: [1, 2, 3] }), 3);
  assert.equal(run("mapping | length", { mapping: { a: 1, b: 2 } }), 2);
  assert.equal(run("values | last", { values: [1, 2] }), 2);
  assert.equal(run("'12' | int"), 12);
  assert.equal(run("'abc' | int"), 0, "a bad conversion falls back to the default, as Jinja does");
  assert.equal(run("'abc' | int(-1)"), -1);
  assert.equal(run("values | join('-')", { values: [1, true] }), "1-True");
  assert.equal(run("'  x ' | trim"), "x");
  assert.equal(run("value | string", { value: null }), "None");
});

test("an unknown filter names the supported set", () => {
  const message = failure("x | groupby('a')", { x: [] });
  assert.match(message, /Unknown filter 'groupby'/);
  assert.match(message, /add_days/);
});

test("an unknown test names the supported set", () => {
  assert.match(failure("x is mapping", { x: 1 }), /Unknown test 'mapping'/);
});

// ── Refusals ─────────────────────────────────────────────────────────────────

test("calls and tuples are refused, not half-supported", () => {
  assert.match(failure("open('x')"), /Function calls are not supported/);
  assert.match(failure("(1, 2)"), /tuples are not supported/);
});

test("a syntax error quotes the expression", () => {
  assert.match(failure("1 +"), /Invalid expression "1 \+"/);
});

// ── The two truthiness rules ─────────────────────────────────────────────────

test("isTruthy is the Aetherius rule, stringified and lowercased", () => {
  for (const value of [true, "True", "true", "TRUE", " yes ", "1", 1]) {
    assert.equal(isTruthy(value), true, `expected ${JSON.stringify(value)} to be truthy`);
  }
  for (const value of [false, "False", "false", "0", "", "no", null, 2, [], [1], {}]) {
    assert.equal(isTruthy(value), false, `expected ${JSON.stringify(value)} to be falsy`);
  }
});

test("pyTruth is Python's own rule, used inside expressions", () => {
  assert.equal(pyTruth(2), true, "a non-zero number is true inside an expression");
  assert.equal(isTruthy(2), false, "but the guard rule says otherwise, and that is deliberate");
  assert.equal(pyTruth([]), false);
  assert.equal(pyTruth([1]), true);
});

test("pythonStr renders values the way str() does", () => {
  assert.equal(pythonStr(true), "True");
  assert.equal(pythonStr(null), "None");
  assert.equal(pythonStr([1, 2]), "[1, 2]");
  assert.equal(pythonStr(["a"]), "['a']");
  assert.equal(pythonStr({ a: 1 }), "{'a': 1}");
  assert.equal(pythonStr("plain"), "plain");
});
