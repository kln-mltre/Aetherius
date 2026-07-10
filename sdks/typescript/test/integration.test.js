/**
 * End-to-end test: spawn the real daemon, run the zero-network self-test Blueprint, and assert the
 * outputs and that events streamed. Requires the `aetherius` package to be importable (via the
 * `aetherius` script or `python3 -m aetherius`); skips cleanly otherwise so the suite still passes
 * on a machine without Python.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";

import { Aetherius } from "../dist/index.js";

/** Return the argv to spawn the daemon, or null if the package is not available. */
function resolveDaemonCommand() {
  for (const base of [["aetherius"], ["python3", "-m", "aetherius"]]) {
    try {
      execFileSync(base[0], [...base.slice(1), "--help"], { stdio: "ignore" });
      return [...base, "serve"];
    } catch {
      // Try the next candidate.
    }
  }
  return null;
}

const command = resolveDaemonCommand();
const blueprint = JSON.parse(
  readFileSync(
    new URL("../../../examples/vector/daemon-selftest.blueprint.json", import.meta.url),
    "utf8",
  ),
);

test(
  "spawns the daemon, runs a Blueprint inline, and streams events to done",
  { skip: command ? false : "aetherius package not importable" },
  async () => {
    const client = new Aetherius({ command });
    const seen = [];
    try {
      const result = await client.run(blueprint, {
        inputs: { subject: "typescript" },
        onEvent: (event) => seen.push(event.type),
      });

      assert.equal(result.status, "succeeded");
      assert.equal(result.outputs.greeting, "hello, typescript");
      assert.ok(seen.includes("done"), `expected a 'done' event, saw: ${seen.join(", ")}`);
    } finally {
      await client.close();
    }
  },
);
