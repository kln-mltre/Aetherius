/**
 * Replay the shared conformance corpus on the embedded engine.
 *
 * TypeScript half of `tests/conformance/harness.py`: same corpus, same comparison, so a
 * divergence between the two engines shows up as a failing case rather than as two suites that
 * happen to disagree. See conformance/README.md.
 */

import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { validateBlueprintData, parseBlueprint } from "../dist/blueprint/loader.js";
import { validateForAct } from "../dist/blueprint/validator.js";
import { AetheriusError } from "../dist/errors.js";

export const ENGINE = "embedded";

export const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const CORPUS_DIR = join(REPO_ROOT, "conformance", "cases");

export const ACCEPTED = "accepted";
export const REJECTED = "rejected";

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
    return { path, name: data.name, data };
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

/** Load and validate the case's Blueprint, reporting what happened rather than throwing. */
export function runCase(kase) {
  try {
    validateForAct(loadBlueprint(kase));
  } catch (error) {
    if (!(error instanceof AetheriusError)) throw error;
    return { outcome: REJECTED, error: error.name, message: error.message };
  }
  return { outcome: ACCEPTED, error: null, message: "" };
}

/** Every way *actual* fails to meet *expected*. An empty array means the case passes. */
export function mismatches(expected, actual) {
  if (actual.outcome !== expected.outcome) {
    // The remaining expectations describe a rejection; reporting them too would be noise.
    return [`expected the Blueprint to be ${expected.outcome}, got ${actual.outcome}`];
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
  return problems;
}

/** A failure message saying what the corpus wanted and what the engine did. */
export function describeFailure(kase, actual, problems) {
  return (
    `${kase.name} (${ENGINE}): ${problems.join("; ")}\n` +
    `  actual: outcome=${actual.outcome} error=${actual.error} message=${JSON.stringify(actual.message)}`
  );
}
