/**
 * The application facade.
 *
 * These tests drive the production path: the real `Aetherius`, the real engine, the real Continuum
 * driver on a jsdom host. What they pin is what an application can rely on — the names it calls,
 * the two output channels, and the three behaviours that cost a leaked WebView or a corrupted run
 * if they regress: cancellation releases the view, two Act II runs cannot overlap, and Act I runs
 * stay concurrent.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { BlueprintValidationError, DependencyError, describeFailure } from "@aetherius/engine";

import { Aetherius } from "../dist/aetherius.js";
import { staticSecrets } from "../dist/secrets/index.js";
import { registerContinuum, webViewLease } from "../dist/registry.js";
import { createDomHost } from "./dom-host.mjs";
import { htmlServer } from "./support.mjs";

const PAGE = `<!doctype html><html><body>
  <h1 id="title">Catalogue</h1>
</body></html>`;

const vector = (steps, extra = {}) => ({
  aetherius: "1.0",
  name: "facade.vector",
  act: "vector",
  ...extra,
  steps,
});

const continuum = (steps, extra = {}) => ({
  aetherius: "1.0",
  name: "facade.continuum",
  act: "continuum",
  inputs: { base_url: { type: "string", required: true } },
  ...extra,
  steps,
});

test("a nominal run reads like the daemon SDK: run(blueprint, { inputs, onEvent })", async () => {
  const client = new Aetherius();
  const events = [];
  const result = await client.run(
    vector([{ id: "one", action: "set", value: "{{ inputs.who }}" }], {
      outputs: { greeting: "{{ steps.one.value }}" },
    }),
    { inputs: { who: "monde" }, onEvent: (event) => events.push(event) },
  );

  assert.equal(result.status, "success");
  assert.deepEqual(result.outputs, { greeting: "monde" });
  // The event stream *is* the progress UI: no application state machine required.
  assert.deepEqual(events.map((event) => event.type), [
    "progress",
    "step_started",
    "step_finished",
    "done",
  ]);
});

test("a Blueprint given as text or as a raw object is validated either way", async () => {
  const client = new Aetherius();
  const text = JSON.stringify(vector([{ id: "one", action: "set", value: 1 }]));
  assert.equal((await client.run(text)).status, "success");

  await assert.rejects(
    () => client.run({ aetherius: "1.0", name: "broken", act: "vector" }),
    (error) => error.name === "BlueprintSchemaError" || error.name === "BlueprintValidationError",
  );
});

test("a run that fails resolves with a Result whose cause is typed", async () => {
  const client = new Aetherius({
    fetch: async () => {
      throw new Error("getaddrinfo ENOTFOUND");
    },
  });
  const result = await client.run(
    vector([{ id: "get", action: "http.request", url: "https://example.invalid/" }]),
  );

  assert.equal(result.status, "failed");
  assert.equal(describeFailure(result).kind, "unavailable");
  assert.equal(describeFailure(result).retryable, true);
});

test("a missing required input is refused before the run, not in the middle of it", async () => {
  const client = new Aetherius();
  await assert.rejects(
    () =>
      client.run(
        vector([{ id: "one", action: "set", value: "{{ inputs.who }}" }], {
          inputs: { who: { type: "string", required: true } },
        }),
      ),
    BlueprintValidationError,
  );
});

test("a declared secret with no value is omitted, and the step that reads it says so", async () => {
  const client = new Aetherius({ secrets: staticSecrets({ known: "value" }) });
  const result = await client.run(
    vector([{ id: "one", action: "set", value: "{{ secrets.missing }}" }], {
      secrets: ["known", "missing"],
    }),
  );

  assert.equal(result.status, "failed");
  // StrictUndefined, at the step that reads it — not a silent empty string three screens later.
  // And `config`, not `data`: the source is fine, the caller supplied nothing (found on a phone).
  assert.equal(describeFailure(result).kind, "config");
  assert.match(result.error, /missing/);
});

test("only declared secrets are asked of the resolver", async () => {
  const asked = [];
  const client = new Aetherius({
    secrets: {
      async resolve(name) {
        asked.push(name);
        return "value";
      },
    },
  });
  await client.run(vector([{ id: "one", action: "set", value: 1 }], { secrets: ["cas_pass"] }));
  assert.deepEqual(asked, ["cas_pass"]);
});

test("a secret passed to run wins over the resolver", async () => {
  const client = new Aetherius({ secrets: staticSecrets({ token: "from-keychain" }) });
  const result = await client.run(
    vector([{ id: "one", action: "set", value: "{{ secrets.token }}" }], {
      secrets: ["token"],
      outputs: { seen: "{{ steps.one.value }}" },
    }),
    { secrets: { token: "from-caller" }, redact: false },
  );
  assert.equal(result.outputs.seen, "from-caller");
});

test("two Act I runs are concurrent: they share nothing", async () => {
  const client = new Aetherius();
  const [first, second] = await Promise.all([
    client.run(vector([{ id: "a", action: "wait", ms: 20 }], { outputs: { who: "first" } })),
    client.run(vector([{ id: "b", action: "wait", ms: 10 }], { outputs: { who: "second" } })),
  ]);
  assert.equal(first.outputs.who, "first");
  assert.equal(second.outputs.who, "second");
  assert.notEqual(first.run_id, second.run_id);
});

test("cancelling a run releases its WebView and reports the run as cancelled", async () => {
  const server = await htmlServer({ "/": PAGE });
  const { host } = createDomHost();
  let disposed = 0;
  const guarded = {
    ...host,
    configure: (...args) => host.configure(...args),
    navigate: (...args) => host.navigate(...args),
    call: (...args) => host.call(...args),
    dispose: async () => {
      disposed += 1;
      await host.dispose();
    },
  };
  registerContinuum(() => guarded);

  try {
    const client = new Aetherius();
    const pending = client.run(
      continuum([
        { action: "navigate", url: "{{ inputs.base_url }}/" },
        // Waits for an element the page will never grow: the run is parked in the agent's
        // auto-wait, which is exactly where a user leaving a screen finds it.
        { action: "wait_for", selector: "#jamais", timeout_ms: 60000 },
      ]),
      { inputs: { base_url: server.baseUrl }, runId: "run-cancel" },
    );

    await sleep(150);
    assert.equal(client.cancel("run-cancel"), true);
    const result = await pending;

    assert.equal(result.status, "failed");
    assert.equal(describeFailure(result).kind, "cancelled");
    // The point of the test: a hidden WebView must not outlive the screen that asked for it.
    assert.equal(disposed, 1, "the WebView was never disposed");
    assert.equal(webViewLease(), undefined, "the WebView lease was never released");
  } finally {
    await server.close();
    registerContinuum();
  }
});

test("a second concurrent Act II run is refused, loudly, instead of corrupting the first", async () => {
  const server = await htmlServer({ "/": PAGE });
  const { host } = createDomHost();
  registerContinuum(() => host);

  try {
    const client = new Aetherius();
    const blueprint = continuum([
      { action: "navigate", url: "{{ inputs.base_url }}/" },
      { action: "wait", ms: 80 },
      { id: "read", action: "extract", outputs: { title: { selector: "#title", as: "text" } } },
    ]);
    const options = { inputs: { base_url: server.baseUrl } };

    const first = client.run(blueprint, { ...options, runId: "run-a" });
    await sleep(20);
    // Not a queue: refusing is what makes the conflict visible. Queuing would hide a parked
    // `confirm` holding the only view for five minutes behind an unexplained delay.
    await assert.rejects(() => client.run(blueprint, { ...options, runId: "run-b" }), DependencyError);

    const result = await first;
    assert.equal(result.status, "success", result.error);
    assert.equal(result.step_results.at(-1).outputs.title, "Catalogue");
    assert.equal(webViewLease(), undefined);
  } finally {
    await server.close();
    registerContinuum();
  }
});

test("close() cancels whatever is still running", async () => {
  const client = new Aetherius();
  const pending = client.run(vector([{ id: "nap", action: "wait", ms: 5000 }]), { runId: "run-x" });
  await sleep(20);
  assert.deepEqual(client.active(), ["run-x"]);

  await client.close();
  const result = await pending;
  assert.equal(describeFailure(result).kind, "cancelled");
  assert.deepEqual(client.active(), []);
});

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
