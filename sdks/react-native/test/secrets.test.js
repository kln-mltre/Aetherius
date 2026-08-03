/**
 * Secrets: where they come from, and where they must never appear.
 *
 * The second half is the one the milestone insists on proving rather than documenting: **no secret
 * appears in any event, in any log, or in the message of an error** — including when a step is
 * skipped by a `when` that references it, which is the case the Python engine solved by publishing
 * the raw expression instead of its rendered value.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { Aetherius } from "../dist/aetherius.js";
import { REDACTED, keychainSecrets, redactText, staticSecrets } from "../dist/secrets/index.js";

const PASSWORD = "s3cr3t-Passw0rd!";

const blueprint = (steps, extra = {}) => ({
  aetherius: "1.0",
  name: "secrets.demo",
  act: "vector",
  secrets: ["cas_pass"],
  ...extra,
  steps,
});

/** Everything an application could see of a run, flattened for a single search. */
function surface(events, result) {
  return JSON.stringify({
    events,
    error: result?.error ?? null,
    cause: result?.cause?.message ?? null,
    outputs: result?.outputs ?? null,
  });
}

test("the keychain adapter reads the store, and a missing entry is an absence", async () => {
  const store = { getItemAsync: async (key) => (key === "cas_pass" ? PASSWORD : null) };
  const resolver = keychainSecrets(store);

  assert.equal(await resolver.resolve("cas_pass"), PASSWORD);
  assert.equal(await resolver.resolve("unknown"), undefined);
});

test("the key mapper lets an application keep its own keychain keys", async () => {
  const store = { getItemAsync: async (key) => (key === "ukit.cas_pass" ? PASSWORD : null) };
  const resolver = keychainSecrets(store, { key: (name) => `ukit.${name}` });
  assert.equal(await resolver.resolve("cas_pass"), PASSWORD);
});

test("a keychain that throws is an absence, not a dead run", async () => {
  // A locked keychain, a corrupt entry: the run may not even need that secret. Letting a platform
  // error escape would kill it for a value nobody asked for.
  const resolver = keychainSecrets({
    getItemAsync: async () => {
      throw new Error("keychain locked");
    },
  });
  assert.equal(await resolver.resolve("cas_pass"), undefined);
});

test("redaction masks the longest values first, so a prefix cannot leak the rest", () => {
  assert.equal(redactText("abc and abcdef", ["abc", "abcdef"]), `${REDACTED} and ${REDACTED}`);
});

test("a secret referenced by a when never reaches the event stream", async () => {
  const client = new Aetherius({ secrets: staticSecrets({ cas_pass: PASSWORD }) });
  const events = [];
  const result = await client.run(
    blueprint([
      // The guard renders to the secret itself: falsy by the Aetherius rule, so the step is skipped
      // and the event reports the *expression*, never its value.
      { id: "guarded", action: "set", when: "{{ secrets.cas_pass }}", value: "never" },
    ]),
    { onEvent: (event) => events.push(event) },
  );

  assert.equal(result.status, "success");
  assert.equal(result.step_results[0].status, "skipped");
  const skipped = events.find((event) => event.type === "step_skipped");
  assert.equal(skipped.data.when, "{{ secrets.cas_pass }}");
  assert.ok(!surface(events, result).includes(PASSWORD), "a secret reached the caller");
});

test("a secret rendered into an assert message never reaches the failure", async () => {
  const client = new Aetherius({ secrets: staticSecrets({ cas_pass: PASSWORD }) });
  const events = [];
  const result = await client.run(
    blueprint([
      {
        id: "check",
        action: "assert",
        condition: "{{ false }}",
        // Python renders an assert message before raising it, and the embedded engine reproduces
        // that; without the facade's curtain, the value would land in `Result.error`.
        message: "refused for {{ secrets.cas_pass }}",
      },
    ]),
    { onEvent: (event) => events.push(event) },
  );

  assert.equal(result.status, "failed");
  assert.match(result.error, /refused for/);
  assert.ok(result.error.includes(REDACTED), `not redacted: ${result.error}`);
  assert.ok(!surface(events, result).includes(PASSWORD), "a secret reached the caller");
});

test("a secret interpolated into a failing URL never reaches the error message", async () => {
  const client = new Aetherius({
    secrets: staticSecrets({ cas_pass: PASSWORD }),
    fetch: async () => {
      throw new Error("getaddrinfo ENOTFOUND");
    },
  });
  const events = [];
  const result = await client.run(
    blueprint([
      {
        id: "get",
        action: "http.request",
        url: "https://example.invalid/?token={{ secrets.cas_pass }}",
      },
    ]),
    { onEvent: (event) => events.push(event) },
  );

  assert.equal(result.status, "failed");
  assert.ok(!surface(events, result).includes(PASSWORD), "a secret reached the caller");
  // The typed cause is scrubbed too: an application that logs `cause.message` must be as safe as
  // one that logs `result.error`.
  assert.ok(!result.cause.message.includes(PASSWORD));
});

test("a secret cited by a Blueprint refused before the run never reaches the thrown error", async () => {
  const client = new Aetherius({ secrets: staticSecrets({ cas_pass: PASSWORD }) });
  await assert.rejects(
    () =>
      client.run(
        blueprint([
          { id: "one", action: "set", value: "{{ secrets.cas_pass }}" },
          { id: "shot", action: "screenshot", path: "out.png" },
        ]),
      ),
    (error) => !String(error.message).includes(PASSWORD),
  );
});

test("redaction can be turned off, and then it really is off", async () => {
  // Documented as a debugging switch, and tested so it does not quietly become a no-op either way.
  const client = new Aetherius({ secrets: staticSecrets({ cas_pass: PASSWORD }), redact: false });
  const result = await client.run(
    blueprint([{ id: "check", action: "assert", condition: "{{ false }}", message: "{{ secrets.cas_pass }}" }]),
  );
  assert.ok(result.error.includes(PASSWORD));
});
