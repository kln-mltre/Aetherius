/**
 * The Continuum driver, driven by the real engine.
 *
 * These tests run whole Blueprints — `RunEngine` resolves the act through the driver registry the
 * package fills on import, exactly as an application would. What they pin is the part that decides
 * whether the same Blueprint behaves the same on both engines: which fields are rendered, what a
 * step publishes, and how a failure is named.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { RunEngine, validateBlueprintData } from "@aetherius/engine";

import { registerContinuum } from "../dist/registry.js";
import { createDomHost } from "./dom-host.mjs";
import { htmlServer } from "./support.mjs";

const HOME = `<!doctype html><html><body>
  <h1 id="title">Catalogue</h1>
  <p class="price">£12,50</p>
  <div class="row"><span class="t">A</span></div>
  <div class="row"><span class="t">B</span></div>
  <form action="/login" method="post">
    <input id="username" name="username" value="">
    <input id="password" name="password" type="password" value="">
    <input type="submit" value="Entrer">
  </form>
</body></html>`;

const pages = {
  "/": HOME,
  "/login": ({ body }) => {
    const sent = new URLSearchParams(body);
    if (sent.get("username") === "kylian" && sent.get("password") === "s3cr3t") {
      return { status: 302, headers: { Location: "/home", "Set-Cookie": "sid=ok; Path=/" }, body: "" };
    }
    return { status: 302, headers: { Location: "/denied" }, body: "" };
  },
  "/home": ({ headers }) => ({
    body: `<html><body><a href="/logout">Se deconnecter</a><span id="who">${headers.cookie ?? "anon"}</span></body></html>`,
  }),
  "/denied": "<html><body><p class='error'>Identifiants refuses</p></body></html>",
};

/** Run *steps* against a fresh server and a fresh jsdom host, through the real engine. */
async function run(blueprint, { inputs, secrets } = {}) {
  const server = await htmlServer(pages);
  const { host } = createDomHost();
  registerContinuum(() => host);
  try {
    const events = [];
    const document = validateBlueprintData(
      { aetherius: "1.0", name: "test.continuum", act: "continuum", ...blueprint },
      "test.json",
    );
    const result = await new RunEngine().run(document, {
      inputs: { base_url: server.baseUrl, ...inputs },
      secrets: secrets ?? {},
      sinks: [{ onEvent: (event) => events.push(event) }],
    });
    return { result, events };
  } finally {
    await server.close();
  }
}

test("a continuum Blueprint runs end to end: navigate, wait_for, extract, evaluate", async () => {
  const { result } = await run({
    steps: [
      { id: "home", action: "navigate", url: "{{ inputs.base_url }}/" },
      { action: "wait_for", selector: "#title", timeout_ms: 3000 },
      {
        id: "page",
        action: "extract",
        outputs: {
          titre: { selector: "#title", as: "text" },
          prix: { selector: ".price", as: "number" },
          lignes: { each: ".row", fields: { t: { selector: ".t", as: "text" } } },
        },
      },
      { id: "js", action: "evaluate", script: "() => document.querySelectorAll('.row').length" },
    ],
    outputs: {
      titre: "{{ steps.page.titre }}",
      prix: "{{ steps.page.prix }}",
      lignes: "{{ steps.page.lignes }}",
      compte: "{{ steps.js.result }}",
    },
  });

  assert.equal(result.status, "success", result.error);
  assert.equal(result.outputs.titre, "Catalogue");
  assert.equal(result.outputs.prix, 12.5);
  assert.deepEqual(result.outputs.lignes, [{ t: "A" }, { t: "B" }]);
  assert.equal(result.outputs.compte, 2);
});

test("navigate publishes its url and, deliberately, no status", async () => {
  const { result } = await run({
    steps: [{ id: "home", action: "navigate", url: "{{ inputs.base_url }}/" }],
    outputs: { url: "{{ steps.home.url }}" },
  });
  assert.equal(result.status, "success", result.error);
  assert.match(result.outputs.url, /^http:\/\/127\.0\.0\.1:\d+\/$/);

  const step = result.step_results[0];
  assert.deepEqual(Object.keys(step.outputs), ["url"], "no 'status' key: a WebView exposes none");
});

test("reading navigate's status raises rather than rendering a wrong value", async () => {
  await assert.rejects(
    run({
      steps: [{ id: "home", action: "navigate", url: "{{ inputs.base_url }}/" }],
      outputs: { status: "{{ steps.home.status }}" },
    }),
    (error) => {
      // StrictUndefined, at the step that reads it, naming the variable. `null` would have been a
      // silent wrong answer, which is the failure mode this engine refuses.
      assert.equal(error.name, "TemplateError");
      assert.match(error.message, /status/);
      return true;
    },
  );
});

test("a login is scripted, and the session carries to the next step", async () => {
  const { result } = await run(
    {
      secrets: ["user", "pass"],
      steps: [
        { action: "navigate", url: "{{ inputs.base_url }}/" },
        { action: "fill", selector: "#username", value: "{{ secrets.user }}" },
        { action: "fill", selector: "#password", value: "{{ secrets.pass }}" },
        { action: "click", selector: "input[type=submit]" },
        { action: "wait_for", selector: "a[href='/logout']", timeout_ms: 3000, on_timeout: "fail:LOGIN_FAILED" },
        { action: "emit", event: "LOGIN_SUCCESS" },
        { id: "session", action: "extract", outputs: { who: { selector: "#who", as: "text" } } },
      ],
      outputs: { who: "{{ steps.session.who }}" },
    },
    { secrets: { user: "kylian", pass: "s3cr3t" } },
  );

  assert.equal(result.status, "success", result.error);
  assert.equal(result.outputs.who, "sid=ok");
});

test("a failed login stops on wait_for with its named code", async () => {
  const { result, events } = await run(
    {
      secrets: ["user", "pass"],
      steps: [
        { action: "navigate", url: "{{ inputs.base_url }}/" },
        { action: "fill", selector: "#username", value: "{{ secrets.user }}" },
        { action: "fill", selector: "#password", value: "{{ secrets.pass }}" },
        { action: "click", selector: "input[type=submit]" },
        {
          id: "gate",
          action: "wait_for",
          selector: "a[href='/logout']",
          timeout_ms: 400,
          on_timeout: "fail:LOGIN_FAILED",
        },
      ],
    },
    { secrets: { user: "kylian", pass: "mauvais" } },
  );

  assert.equal(result.status, "failed");
  assert.match(result.error, /wait_for timed out/);
  const failed = result.step_results.find((step) => step.step_id === "gate");
  assert.equal(failed.status, "failed");
  assert.ok(events.some((event) => event.type === "error" && event.step_id === "gate"));
});

test("history steps publish the url they landed on", async () => {
  const { result } = await run({
    steps: [
      { action: "navigate", url: "{{ inputs.base_url }}/" },
      { action: "navigate", url: "{{ inputs.base_url }}/denied" },
      { id: "retour", action: "back" },
      { id: "avant", action: "forward" },
      { id: "encore", action: "reload" },
    ],
    outputs: {
      retour: "{{ steps.retour.url }}",
      avant: "{{ steps.avant.url }}",
      encore: "{{ steps.encore.url }}",
    },
  });

  assert.equal(result.status, "success", result.error);
  assert.match(result.outputs.retour, /\/$/);
  assert.match(result.outputs.avant, /\/denied$/);
  assert.match(result.outputs.encore, /\/denied$/);
});

test("a selector may be templated, like every other rendered field", async () => {
  const { result } = await run(
    {
      inputs: { cible: { type: "string", required: true } },
      steps: [
        { action: "navigate", url: "{{ inputs.base_url }}/" },
        { id: "lu", action: "extract", outputs: { v: { selector: "{{ inputs.cible }}", as: "text" } } },
      ],
      outputs: { v: "{{ steps.lu.v }}" },
    },
    { inputs: { cible: "#title" } },
  );
  assert.equal(result.status, "success", result.error);
  assert.equal(result.outputs.v, "Catalogue");
});

test("evaluate passes its arg as JSON and honours an expression as well as a function", async () => {
  const { result } = await run({
    steps: [
      { action: "navigate", url: "{{ inputs.base_url }}/" },
      { id: "fn", action: "evaluate", script: "(arg) => arg.n * 2", arg: { n: 21 } },
      { id: "expr", action: "evaluate", script: "document.title || 'sans titre'" },
      { id: "vide", action: "evaluate", script: "() => undefined" },
    ],
    outputs: {
      fn: "{{ steps.fn.result }}",
      expr: "{{ steps.expr.result }}",
      vide: "{{ steps.vide.result }}",
    },
  });
  assert.equal(result.status, "success", result.error);
  assert.equal(result.outputs.fn, 42);
  assert.equal(result.outputs.expr, "sans titre");
  // `undefined` cannot cross JSON, and Python's `page.evaluate` returns `None` for it: the answer
  // is null on both engines. The bare-expression rule then hands the raw value back, not a string.
  assert.equal(result.outputs.vide, null);
});

test("an evaluate that throws is a clean step failure, not a crash", async () => {
  const { result } = await run({
    steps: [
      { action: "navigate", url: "{{ inputs.base_url }}/" },
      { id: "boom", action: "evaluate", script: "() => { throw new Error('casse'); }" },
    ],
  });
  assert.equal(result.status, "failed");
  assert.match(result.error, /evaluate: casse/);
});

test("without a mounted WebView the run says which import is missing", async () => {
  registerContinuum(() => undefined);
  const server = await htmlServer(pages);
  try {
    const document = validateBlueprintData(
      {
        aetherius: "1.0",
        name: "test.nohost",
        act: "continuum",
        steps: [{ action: "navigate", url: `${server.baseUrl}/` }],
      },
      "test.json",
    );
    await assert.rejects(new RunEngine().run(document), (error) => {
      assert.equal(error.name, "DependencyError");
      assert.match(error.message, /AetheriusWebView/);
      return true;
    });
  } finally {
    await server.close();
  }
});

test("the Blueprint's session options reach the view", async () => {
  const server = await htmlServer(pages);
  const { host, page } = createDomHost();
  registerContinuum(() => host);
  try {
    const document = validateBlueprintData(
      {
        aetherius: "1.0",
        name: "test.session",
        act: "continuum",
        options: { session: { profile: "demo", persist: true }, debug: true },
        steps: [{ action: "navigate", url: `${server.baseUrl}/` }],
      },
      "test.json",
    );
    const result = await new RunEngine().run(document, { sinks: [] });
    assert.equal(result.status, "success", result.error);
    assert.equal(page.session.persist, true, "persist reaches the view: shared cookie store");
    assert.equal(page.session.debug, true, "debug reaches the view: it becomes visible");
  } finally {
    await server.close();
  }
});

test("a second run on the same host works: dispose releases the view, not the host", async () => {
  // The host belongs to the mounted component and outlives the runs it serves. Teardown disposes
  // it; if that were final, run #2 would fail — invisible on a first launch, fatal on the second
  // tap of the Run button.
  const server = await htmlServer(pages);
  const { host, page } = createDomHost();
  registerContinuum(() => host);
  try {
    const document = validateBlueprintData(
      {
        aetherius: "1.0",
        name: "test.twice",
        act: "continuum",
        steps: [
          { action: "navigate", url: `${server.baseUrl}/` },
          { id: "lu", action: "extract", outputs: { t: { selector: "#title", as: "text" } } },
        ],
        outputs: { t: "{{ steps.lu.t }}" },
      },
      "test.json",
    );

    const first = await new RunEngine().run(document, { sinks: [] });
    assert.equal(first.status, "success", first.error);
    assert.equal(first.outputs.t, "Catalogue");

    const second = await new RunEngine().run(document, { sinks: [] });
    assert.equal(second.status, "success", second.error);
    assert.equal(second.outputs.t, "Catalogue");

    // And the session options were applied again, not assumed to still hold.
    assert.equal(page.session.persist, false);
  } finally {
    await server.close();
  }
});

test("an isolated session starts each run with an empty store", async () => {
  const server = await htmlServer(pages);
  const { host } = createDomHost();
  registerContinuum(() => host);
  try {
    const login = validateBlueprintData(
      {
        aetherius: "1.0",
        name: "test.session.isolated",
        act: "continuum",
        secrets: ["user", "pass"],
        steps: [
          { action: "navigate", url: `${server.baseUrl}/` },
          { action: "fill", selector: "#username", value: "{{ secrets.user }}" },
          { action: "fill", selector: "#password", value: "{{ secrets.pass }}" },
          { action: "click", selector: "input[type=submit]" },
          { action: "wait_for", selector: "a[href='/logout']", timeout_ms: 3000 },
          { id: "who", action: "extract", outputs: { v: { selector: "#who", as: "text" } } },
        ],
        outputs: { who: "{{ steps.who.v }}" },
      },
      "test.json",
    );
    const secrets = { user: "kylian", pass: "s3cr3t" };
    const first = await new RunEngine().run(login, { secrets, sinks: [] });
    assert.equal(first.outputs.who, "sid=ok");

    // Second run, session NOT persisted: the store was dropped with the view, so /home is anonymous
    // until this run logs in again — which is exactly what `persist: false` promises.
    const anonymous = validateBlueprintData(
      {
        aetherius: "1.0",
        name: "test.session.anon",
        act: "continuum",
        steps: [
          { action: "navigate", url: `${server.baseUrl}/home` },
          { id: "who", action: "extract", outputs: { v: { selector: "#who", as: "text" } } },
        ],
        outputs: { who: "{{ steps.who.v }}" },
      },
      "test.json",
    );
    const second = await new RunEngine().run(anonymous, { sinks: [] });
    assert.equal(second.outputs.who, "anon");
  } finally {
    await server.close();
  }
});

test("a page that never answers produces the failure the Blueprint named", async () => {
  // Found on an iPhone: a wrong CAS password made `wait_for` expire, but the *agent's* own deadline
  // never came back — iOS throttles timers in a WebView that is not on screen, and this engine keeps
  // it off screen. The run reported "the operation did not answer", classified as an engine bug,
  // when the Blueprint had already said what to call it. The caller is the only dependable clock.
  const silent = {
    configure: async () => {},
    navigate: async (url) => url,
    goBack: async () => "",
    goForward: async () => "",
    reload: async () => "",
    call: async () => {
      const { NoAnswerError } = await import("../dist/webview/rpc.js");
      throw new NoAnswerError("operation 'wait_for' did not answer within 200 ms");
    },
    evaluate: async () => null,
    settleAfterAction: async () => {},
    currentUrl: () => "",
    dispose: async () => {},
  };
  registerContinuum(() => silent);

  try {
    const result = await new RunEngine().run(
      validateBlueprintData(
        {
          aetherius: "1.0",
          name: "test.silence",
          act: "continuum",
          options: { timeout_ms: 200 },
          steps: [
            { action: "navigate", url: "https://example.invalid/" },
            {
              action: "wait_for",
              selector: ".success",
              timeout_ms: 200,
              on_timeout: "fail:LOGIN_FAILED",
            },
          ],
        },
        "silence.json",
      ),
      { sinks: [] },
    );

    assert.equal(result.status, "failed");
    assert.equal(result.cause.name, "StepTimeoutError");
    assert.equal(result.cause.code, "LOGIN_FAILED", "the named failure must survive the silence");
  } finally {
    registerContinuum();
  }
});
