/**
 * Anti-drift guards for the WebView half of the engine.
 *
 * Three things could rot silently here, and each would fail on a device rather than in CI:
 *
 *   - the **agent bundle** could be built from older sources than the ones on disk. A driver
 *     talking to a stale agent fails in ways that look like a browser problem, which is the worst
 *     kind of bug to chase;
 *   - the **operation vocabulary** could drift between the protocol and the table that implements
 *     it, so an action would validate and then be refused mid-run;
 *   - this package could start **building code at runtime**. It runs on Hermes, which supports
 *     neither `eval` nor `new Function` (docs/phase-3/README.md, decision 4). The engine has this
 *     guard; the package that ships the driver needs it too.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { AGENT_SHA256, AGENT_SOURCE } from "../dist/generated/agent-source.js";
import { OPS } from "../dist/webview/protocol.js";
import { AGENT_ACTIONS } from "../dist/continuum/actions.js";

const PACKAGE = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const WORKSPACE = resolve(PACKAGE, "..");

const FORBIDDEN = [
  { label: "new Function", pattern: /\bnew\s+Function\s*\(/ },
  // Bare `eval(` only: `.eval(` is a method on someone else's object, not the global.
  { label: "eval(", pattern: /(^|[^.\w$])eval\s*\(/ },
];

const CODE = /\.(?:js|mjs|cjs)$/;

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

/** The digest `scripts/build-agent.mjs` computes, recomputed from the files on disk. */
function agentDigest() {
  const dir = join(PACKAGE, "src", "webview", "agent");
  const files = [];
  const walk = (from) => {
    for (const entry of readdirSync(from, { withFileTypes: true })) {
      const path = join(from, entry.name);
      if (entry.isDirectory()) walk(path);
      else if (entry.name.endsWith(".ts")) files.push(path);
    }
  };
  walk(dir);
  files.push(join(PACKAGE, "src", "webview", "protocol.ts"));
  files.sort();

  const hash = createHash("sha256");
  for (const path of files) {
    hash.update(relative(PACKAGE, path).split("\\").join("/"), "utf8");
    hash.update("\0", "utf8");
    hash.update(readFileSync(path, "utf8"), "utf8");
    hash.update("\0", "utf8");
  }
  return hash.digest("hex");
}

test("the bundled agent is not stale", () => {
  assert.equal(
    AGENT_SHA256,
    agentDigest(),
    "the agent bundle was built from other sources — run `npm run build`",
  );
});

test("the bundled agent is one self-contained script", () => {
  assert.ok(AGENT_SOURCE.length > 1000, "the bundle looks empty");
  assert.ok(!AGENT_SOURCE.includes("import "), "an injected script cannot import");
  assert.ok(!AGENT_SOURCE.includes("require("), "an injected script cannot require");
  for (const { label, pattern } of FORBIDDEN) {
    assert.ok(!pattern.test(AGENT_SOURCE), `the agent must not build code at runtime (${label})`);
  }
});

test("the operation vocabulary and the action table agree", () => {
  // The protocol names the closed vocabulary; the driver's table is what actually sends it. A
  // vocabulary that drifted from its table would validate a Blueprint and refuse it mid-run.
  assert.deepEqual([...OPS].sort(), Object.keys(AGENT_ACTIONS).sort());
});

test("this package builds no code at runtime", () => {
  assert.deepEqual(offenders(join(PACKAGE, "dist")), []);
});

test("the package's public surface is one door", () => {
  // An application should never have to know that the error model lives in the neutral package or
  // that the WebView lease lives three directories down. A missing re-export is not a compile error
  // for the *application* — it is an import that fails on a phone.
  //
  // Read rather than imported: the barrel pulls `react-native-webview`, a peer dependency this
  // workspace deliberately does not install (see react-native-webview.d.ts). Every other test here
  // imports the module it exercises for the same reason.
  const barrel = readFileSync(join(PACKAGE, "dist", "index.js"), "utf8");
  const exported = new Set(
    [...barrel.matchAll(/^export \{([^}]*)\}/gms)]
      .flatMap((match) => match[1].split(","))
      .map((name) => name.trim().split(/\s+as\s+/).pop())
      .filter(Boolean),
  );

  for (const name of [
    "Aetherius",
    "AetheriusConfirm",
    "AetheriusWebView",
    "BlueprintRegistry",
    "ConfirmGateway",
    "describeFailure",
    "keychainSecrets",
    "memoryCache",
    "parseManifest",
    "staticSecrets",
    "useAetheriusRun",
    "useApprovalRequest",
  ]) {
    assert.ok(exported.has(name), `'${name}' is not exported by the package`);
  }
});

test("no runtime dependency builds code at runtime", () => {
  const lock = JSON.parse(readFileSync(join(WORKSPACE, "package-lock.json"), "utf8"));
  const declared = (key) => Object.keys(lock.packages[key]?.dependencies ?? {});

  const seen = new Set();
  const queue = declared("react-native");
  assert.ok(queue.length > 0, "the package declares no runtime dependency; check the lockfile key");

  while (queue.length > 0) {
    const name = queue.pop();
    if (seen.has(name) || name.startsWith("@aetherius/")) continue;
    seen.add(name);
    queue.push(...declared(`node_modules/${name}`));
  }
  for (const name of [...seen].sort()) {
    assert.deepEqual(
      offenders(join(WORKSPACE, "node_modules", name)),
      [],
      `${name} would break on Hermes`,
    );
  }
});
