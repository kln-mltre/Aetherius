/**
 * The acceptance criterion of milestone 3-D: **no parameter is ever interpolated into the source of
 * an injected script**.
 *
 * This is the bug the hand-written hidden WebViews carry — a value spliced between quotes, and a
 * password containing an apostrophe breaks the script (or worse, ends it and starts something
 * else). Making it impossible is not a matter of escaping carefully; it is a matter of parameters
 * crossing as JSON the page *parses*, never as text the page *compiles*.
 *
 * The structural assertion is the important one: an injected order matches a **fixed template**
 * whose only variable part is one well-formed JSON string literal. Nothing of the value can be
 * outside it, whatever the value contains — which is a stronger statement than hunting for
 * substrings, and one that stays true for hostile inputs nobody thought of.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { AgentBridge } from "../dist/webview/rpc.js";
import { PROTOCOL_VERSION } from "../dist/webview/protocol.js";
import { openPage } from "./support.mjs";

/** Everything that has ever broken a string-template script, in one value. */
const HOSTILE = `a'b"c\`d\\e </script><script>window.__pwned = 1;</script> éà ${"${"}injected}`;

/**
 * The whole order, and nothing but the order: the constant call, one JSON string literal, the
 * trailing `true;` iOS needs. A value that escaped the literal could not match this.
 */
const ORDER_SHAPE = /^window\.__aetherius\.handle\("(?:[^"\\]|\\.)*"\);\ntrue;$/;

const FORM = `<!doctype html><html><body>
  <form id="login" action="/echo" method="post">
    <input id="password" name="password" type="password" value="">
    <textarea id="notes" name="notes"></textarea>
  </form>
</body></html>`;

/** Record what actually goes into the page, through the same seam the WebView injects through. */
function watchInjections(page) {
  const seen = [];
  const real = page.inject.bind(page);
  page.inject = (source) => {
    seen.push(source);
    real(source);
  };
  return seen;
}

function escapeHtml(text) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

test("a hostile value reaches the field intact, and the source stays a constant template", async () => {
  const opened = await openPage({ "/": FORM });
  try {
    const injected = watchInjections(opened.page);

    await opened.host.call("fill", { selector: "#password", value: HOSTILE }, 3000);

    const read = await opened.host.evaluate(
      "() => document.getElementById('password').value",
      null,
      3000,
    );
    assert.equal(read, HOSTILE, "the value must survive the round trip byte for byte");

    const pwned = await opened.host.evaluate("() => window.__pwned || null", null, 3000);
    assert.equal(pwned, null, "the payload must not have executed");

    const order = injected[0];
    assert.match(order, ORDER_SHAPE, "the value is confined to one JSON string literal");
    const parsed = JSON.parse(JSON.parse(/handle\((".*")\);/s.exec(order)[1]));
    assert.equal(parsed.params.value, HOSTILE);
  } finally {
    await opened.close();
  }
});

test("typing a hostile value character by character is just as safe", async () => {
  const opened = await openPage({ "/": FORM });
  try {
    const injected = watchInjections(opened.page);

    await opened.host.call("type", { selector: "#notes", text: HOSTILE }, 5000);
    const read = await opened.host.evaluate(
      "() => document.getElementById('notes').value",
      null,
      5000,
    );
    assert.equal(read, HOSTILE);
    assert.match(injected[0], ORDER_SHAPE);
  } finally {
    await opened.close();
  }
});

test("a multi-line hostile value survives in a textarea, newlines included", async () => {
  const withNewlines = `${HOSTILE}\nligne deux\ttabulee`;
  const opened = await openPage({ "/": FORM });
  try {
    const injected = watchInjections(opened.page);
    await opened.host.call("fill", { selector: "#notes", value: withNewlines }, 3000);
    const read = await opened.host.evaluate(
      "() => document.getElementById('notes').value",
      null,
      3000,
    );
    assert.equal(read, withNewlines);
    assert.match(injected[0], ORDER_SHAPE, "a newline must not break the order out of its literal");
  } finally {
    await opened.close();
  }
});

test("a hostile value survives a real form submission", async () => {
  const opened = await openPage({
    "/": FORM,
    "/echo": ({ body }) => ({ body: `<html><body><pre id="seen">${escapeHtml(body)}</pre></body></html>` }),
  });
  try {
    await opened.host.call("fill", { selector: "#password", value: HOSTILE }, 3000);
    await opened.host.call("press", { selector: "#password", key: "Enter" }, 3000);
    await opened.host.settleAfterAction(3000);

    const seen = await opened.host.call(
      "extract",
      { outputs: { body: { selector: "#seen", as: "text" } } },
      3000,
    );
    const sent = new URLSearchParams(seen.body).get("password");
    // An <input> is a single-line control: a browser strips CR/LF from its value, and so does this.
    assert.equal(sent, HOSTILE.replace(/[\r\n]/g, ""));
  } finally {
    await opened.close();
  }
});

test("the order carrying a hostile value is one JSON literal, and it parses back", () => {
  const injected = [];
  const bridge = new AgentBridge((source) => injected.push(source));
  bridge.receive(JSON.stringify({ aeth: PROTOCOL_VERSION, gen: 1, ready: true, url: "http://x/" }));
  void bridge.call("fill", { selector: "#password", value: HOSTILE }, 1000).catch(() => {});

  assert.match(injected[0], ORDER_SHAPE);
  const order = JSON.parse(JSON.parse(/handle\((".*")\);/s.exec(injected[0])[1]));
  assert.equal(order.params.value, HOSTILE);
  assert.equal(order.op, "fill");
});

test("evaluate is the one exception, and only its script crosses as source", () => {
  const injected = [];
  const bridge = new AgentBridge((source) => injected.push(source));
  bridge.receive(JSON.stringify({ aeth: PROTOCOL_VERSION, gen: 1, ready: true, url: "http://x/" }));
  void bridge
    .callRaw("evaluate", (id) => `SCRIPT(${JSON.stringify(id)})`, 1000)
    .catch(() => {});
  assert.equal(injected[0], 'SCRIPT("c1")');
});
