/**
 * Replay the shared conformance corpus on the embedded engine.
 *
 * TypeScript half of `tests/conformance/harness.py`: same corpus, same comparison, so a
 * divergence between the two engines shows up as a failing case rather than as two suites that
 * happen to disagree.
 *
 * A case declares its `kind`. `validation` (the default) answers "is this Blueprint accepted"; the
 * execution kinds added at milestone 3-B answer "and does it produce the same value". Adding a
 * *case* touches no executor; adding a *kind* touches both, on purpose. See conformance/README.md.
 */

import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { validateBlueprintData, parseBlueprint } from "../dist/blueprint/loader.js";
import { validateForAct } from "../dist/blueprint/validator.js";
import { AetheriusError } from "../dist/errors.js";
import { isTruthy } from "../dist/expr/index.js";
import { dispatchExtract } from "../dist/extraction/index.js";
import { renderValue } from "../dist/template.js";

export const ENGINE = "embedded";

export const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const CORPUS_DIR = join(REPO_ROOT, "conformance", "cases");

export const ACCEPTED = "accepted";
export const REJECTED = "rejected";
export const RENDERED = "rendered";
export const ERROR = "error";

const MISSING = Symbol("no value");

function jsonFiles(dir) {
  return readdirSync(dir, { withFileTypes: true, recursive: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
    .map((entry) => join(entry.parentPath ?? entry.path, entry.name))
    .sort();
}

/** Every case in the corpus, sorted by path so both engines enumerate in the same order. */
export function loadCases() {
  return jsonFiles(CORPUS_DIR).map((path) => {
    const data = JSON.parse(readFileSync(path, "utf8"));
    return { path, name: data.name, kind: data.kind ?? "validation", data };
  });
}

export function expectationFor(kase) {
  const expected = kase.data.expect?.[ENGINE];
  if (expected === undefined) {
    throw new Error(`${kase.name}: no expectation for engine '${ENGINE}'`);
  }
  return expected;
}

function loadBlueprint(kase) {
  if (kase.data.blueprint_path !== undefined) {
    const path = join(REPO_ROOT, kase.data.blueprint_path);
    return parseBlueprint(readFileSync(path, "utf8"), kase.data.blueprint_path);
  }
  if (kase.data.blueprint_text !== undefined) {
    return parseBlueprint(kase.data.blueprint_text, `${kase.name}.blueprint.json`);
  }
  return validateBlueprintData(kase.data.blueprint, `${kase.name}.json`);
}

function execute(kase) {
  switch (kase.kind) {
    case "expression":
      return renderValue(kase.data.value, kase.data.context ?? {});
    case "extraction":
      return dispatchExtract(kase.data.body, kase.data.spec);
    case "truthy":
      return kase.data.values.map(isTruthy);
    default:
      throw new Error(`${kase.name}: unknown case kind '${kase.kind}'`);
  }
}

/** Run the case through the production code path, reporting what happened rather than throwing. */
export function runCase(kase) {
  if (kase.kind === "validation") {
    try {
      validateForAct(loadBlueprint(kase));
    } catch (error) {
      if (!(error instanceof AetheriusError)) throw error;
      return { outcome: REJECTED, error: error.name, message: error.message, value: MISSING };
    }
    return { outcome: ACCEPTED, error: null, message: "", value: MISSING };
  }

  try {
    return { outcome: RENDERED, error: null, message: "", value: execute(kase) };
  } catch (error) {
    if (!(error instanceof AetheriusError)) throw error;
    return { outcome: ERROR, error: error.name, message: error.message, value: MISSING };
  }
}

/** A value's comparable form. Both engines serialise the same way, keys sorted. */
export function canonical(value) {
  if (value === undefined) return "null";
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(", ")}]`;
  const keys = Object.keys(value).sort();
  return `{${keys.map((key) => `${JSON.stringify(key)}: ${canonical(value[key])}`).join(", ")}}`;
}

/** Every way *actual* fails to meet *expected*. An empty array means the case passes. */
export function mismatches(expected, actual) {
  if (actual.outcome !== expected.outcome) {
    // Name what the case is about: a validation case judges a Blueprint, an execution case judges
    // a rendered value. The remaining expectations describe the other branch — noise, here.
    const subject =
      expected.outcome === ACCEPTED || expected.outcome === REJECTED ? "the Blueprint" : "the case";
    return [`expected ${subject} to be ${expected.outcome}, got ${actual.outcome}`];
  }

  const problems = [];
  if (expected.error !== undefined && actual.error !== expected.error) {
    problems.push(`expected error ${expected.error}, got ${actual.error}`);
  }
  for (const fragment of expected.message_contains ?? []) {
    if (!actual.message.includes(fragment)) {
      problems.push(`message does not contain ${JSON.stringify(fragment)}`);
    }
  }
  if (Object.prototype.hasOwnProperty.call(expected, "value")) {
    if (actual.value === MISSING) {
      problems.push("expected a value, the case produced none");
    } else if (canonical(actual.value) !== canonical(expected.value)) {
      problems.push(`expected value ${canonical(expected.value)}`);
    }
  }
  return problems;
}

/** A failure message saying what the corpus wanted and what the engine did. */
export function describeFailure(kase, actual, problems) {
  const detail = actual.value === MISSING ? "" : ` value=${canonical(actual.value)}`;
  return (
    `${kase.name} (${ENGINE}): ${problems.join("; ")}\n` +
    `  actual: outcome=${actual.outcome} error=${actual.error} ` +
    `message=${JSON.stringify(actual.message)}${detail}`
  );
}
