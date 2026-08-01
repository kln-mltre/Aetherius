/**
 * The client's public enumerations must match `contracts/` — the source of truth both engines and
 * every SDK conform to. Written after this very file's absence let the event list fall two types
 * behind the daemon (see milestone 3-A).
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { RUN_EVENT_TYPES } from "../dist/events.js";

const CONTRACTS = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "contracts");

test("the run event enumeration covers exactly contracts/events.schema.json", () => {
  const schema = JSON.parse(readFileSync(join(CONTRACTS, "events.schema.json"), "utf8"));
  assert.deepEqual([...RUN_EVENT_TYPES].sort(), [...schema.properties.type.enum].sort());
});
