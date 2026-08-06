/**
 * Value rendering: the bare-expression rule, recursion, and Python-faithful interpolation.
 *
 * The bare-expression rule is the one a JavaScript port silently breaks: get it wrong and every
 * `outputs` entry returning a collection keeps succeeding, with a string where the data was.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { TemplateError } from "../dist/errors.js";
import { renderValue } from "../dist/template.js";

const render = (value, ctx = {}) => renderValue(value, ctx);

function failure(value, ctx = {}) {
  try {
    render(value, ctx);
  } catch (error) {
    assert.ok(error instanceof TemplateError, `unexpected error: ${error}`);
    return error.message;
  }
  return assert.fail(`expected ${JSON.stringify(value)} to raise`);
}

test("a bare expression returns the raw value", () => {
  const events = [{ id: 1 }, { id: 2 }];
  assert.deepEqual(render("{{ steps.week.events }}", { steps: { week: { events } } }), events);
  assert.equal(render("{{ n }}", { n: 42 }), 42);
  assert.equal(render("{{ flag }}", { flag: true }), true);
  assert.equal(render("{{ nothing }}", { nothing: null }), null);
  assert.deepEqual(render("  {{ mapping }}  ", { mapping: { a: 1 } }), { a: 1 });
});

test("text around an expression makes the result a string", () => {
  assert.equal(render("ids: {{ values }}", { values: [1, 2] }), "ids: [1, 2]");
  assert.equal(render("{{ vars.domain }}/calendar", { vars: { domain: "https://a.fr" } }), "https://a.fr/calendar");
});

test("interpolated values are stringified the way Python does", () => {
  assert.equal(render("flag: {{ x }} none: {{ y }}", { x: true, y: null }), "flag: True none: None");
});

test("several expressions interpolate in one string", () => {
  const ctx = { a: 1, b: 2 };
  assert.equal(render("x {{ a }} y {{ b }} z", ctx), "x 1 y 2 z");
});

test("a string that both starts and ends with an expression interpolates", () => {
  // Until milestone 3-G both engines *refused* this: the bare-expression pattern backtracked past
  // the first `}}` and read the whole string as one malformed expression. The first reference
  // Blueprint hit it on `"{{ vars.api }}/{{ inputs.id }}"` — a URL built from two variables. Fixed
  // on both engines the same day, which is what keeps the invariant the old test protected.
  assert.equal(render("{{ a }} {{ b }}", { a: 1, b: 2 }), "1 2");
  assert.equal(render("{{ a }}/{{ b }}", { a: 1, b: 2 }), "1/2");
  assert.equal(render("x {{ a }} {{ b }}", { a: 1, b: 2 }), "x 1 2");
});

test("the bare expression rule survives the fix", () => {
  // The counterpart: exactly one expression still yields the raw object, whitespace aside.
  assert.deepEqual(render("  {{ rows }}  ", { rows: [1, 2] }), [1, 2]);
});

test("a string without any expression passes through untouched", () => {
  assert.equal(render("plain text"), "plain text");
  assert.equal(render("100% sure"), "100% sure");
});

test("non-string scalars pass through unchanged", () => {
  assert.equal(render(5), 5);
  assert.equal(render(false), false);
  assert.equal(render(null), null);
});

test("arrays and objects render recursively", () => {
  const rendered = render({ nested: ["{{ x }}", { k: "{{ x }}" }], raw: 5 }, { x: [1, 2] });
  assert.deepEqual(rendered, { nested: [[1, 2], { k: [1, 2] }], raw: 5 });
});

test("an undefined variable raises rather than rendering empty", () => {
  assert.match(failure("{{ missing }}"), /Undefined variable in expression: 'missing'/);
  assert.match(failure("value: {{ missing }}"), /Undefined variable in expression: 'missing'/);
  assert.match(failure("{{ steps.x.missing }}", { steps: { x: {} } }), /steps\.x\.missing/);
});
