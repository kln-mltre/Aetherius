/**
 * The constraint of the phase, made executable: nothing this package ships may build code at
 * runtime.
 *
 * Hermes supports neither `eval` nor `new Function` (docs/phase-3/README.md, decision 4). That is
 * why the JSON Schema validator is precompiled at build time and why the expression evaluator is
 * hand-written. It is also why the HTML stack was chosen after checking it: `htmlparser2`,
 * `domhandler`, `domutils` and `css-select` compile selectors into composed closures, not into
 * generated source. A dependency bump that changed that would be invisible until an app crashed on
 * a device — so it is checked here, on the real dependency closure resolved from the lockfile.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ENGINE = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const WORKSPACE = resolve(ENGINE, "..");

const FORBIDDEN = [
  { label: "new Function", pattern: /\bnew\s+Function\s*\(/ },
  // Bare `eval(` only: `.eval(` is a method on someone else's object, not the global.
  { label: "eval(", pattern: /(^|[^.\w$])eval\s*\(/ },
];

const CODE = /\.(?:js|mjs|cjs)$/;

/** Every runtime dependency of the engine, transitively, from the committed lockfile. */
function runtimeClosure() {
  const lock = JSON.parse(readFileSync(join(WORKSPACE, "package-lock.json"), "utf8"));
  const declared = (key) => Object.keys(lock.packages[key]?.dependencies ?? {});

  const seen = new Set();
  const queue = declared("engine");
  assert.ok(queue.length > 0, "the engine declares no runtime dependency; check the lockfile key");

  while (queue.length > 0) {
    const name = queue.pop();
    if (seen.has(name)) continue;
    seen.add(name);
    queue.push(...declared(`node_modules/${name}`));
  }
  return [...seen].sort();
}

function* jsFiles(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules") continue;
      yield* jsFiles(path);
    } else if (CODE.test(entry.name)) {
      yield path;
    }
  }
}

function offenders(dir) {
  const found = [];
  for (const path of jsFiles(dir)) {
    const source = readFileSync(path, "utf8");
    for (const { label, pattern } of FORBIDDEN) {
      if (pattern.test(source)) found.push(`${path}: ${label}`);
    }
  }
  return found;
}

test("the engine's own output builds no code at runtime", () => {
  // Includes the precompiled schema validator: Ajv's standalone output is ordinary JavaScript,
  // and this is what proves it stayed that way.
  assert.deepEqual(offenders(join(ENGINE, "dist")), []);
});

test("no runtime dependency builds code at runtime", () => {
  const closure = runtimeClosure();
  assert.ok(closure.includes("htmlparser2"), "the HTML stack should be in the closure");
  for (const name of closure) {
    assert.deepEqual(
      offenders(join(WORKSPACE, "node_modules", name)),
      [],
      `${name} would break on Hermes`,
    );
  }
});
