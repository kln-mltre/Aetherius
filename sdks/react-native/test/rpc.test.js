/**
 * The correlated RPC, driven directly.
 *
 * No DOM here on purpose: what is under test is the bookkeeping between the driver and a page —
 * ids, deadlines, split messages, and the generation token that decides whether an answer still
 * belongs to anybody. Those are the failure modes a hand-written WebView never has to think about
 * until the day two reads overlap or a page navigates mid-call.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { NetworkError, TimeoutError, describeFailure } from "@aetherius/engine";

import { AgentBridge } from "../dist/webview/rpc.js";
import { BridgedHost } from "../dist/webview/bridged-host.js";
import { PROTOCOL_VERSION } from "../dist/webview/protocol.js";

/** The order the driver just injected, recovered from the source it produced. */
function orderIn(source) {
  const match = /handle\((".*")\);/s.exec(source);
  assert.ok(match, `no order found in injected source: ${source}`);
  return JSON.parse(JSON.parse(match[1]));
}

/** A `PageControl` double that records what the host asked of the view. */
function recordingPage(injected = []) {
  const calls = [];
  return {
    calls,
    load: (url) => calls.push(`load:${url}`),
    goBack: () => calls.push("goBack"),
    goForward: () => calls.push("goForward"),
    reload: () => calls.push("reload"),
    inject: (source) => injected.push(source),
    applySession: () => true,
    destroy: () => calls.push("destroy"),
  };
}

function bridgeWithAgent(gen = 1) {
  const injected = [];
  const bridge = new AgentBridge((source) => injected.push(source));
  bridge.receive(JSON.stringify({ aeth: PROTOCOL_VERSION, gen, ready: true, url: "http://x/" }));
  return { bridge, injected, gen };
}

function answer(bridge, gen, id, payload) {
  bridge.receive(JSON.stringify({ aeth: PROTOCOL_VERSION, gen, id, ...payload }));
}

test("two concurrent calls keep their own answers, whatever the order they come back", async () => {
  const { bridge, injected, gen } = bridgeWithAgent();

  const first = bridge.call("extract", { outputs: { a: {} } }, 2000);
  const second = bridge.call("extract", { outputs: { b: {} } }, 2000);

  const [one, two] = injected.map(orderIn);
  assert.notEqual(one.id, two.id, "two calls must not share an id");

  // Answered in reverse: correlation is the only thing that can keep them apart.
  answer(bridge, gen, two.id, { ok: true, value: { which: "second" } });
  answer(bridge, gen, one.id, { ok: true, value: { which: "first" } });

  assert.deepEqual(await first, { which: "first" });
  assert.deepEqual(await second, { which: "second" });
});

test("a call that is never answered fails at a known time", async () => {
  const { bridge } = bridgeWithAgent();
  // `NoAnswerError`: the caller is the only dependable clock, and the driver renames this silence
  // into the failure the Blueprint chose (see continuum/driver.ts).
  await assert.rejects(bridge.call("extract", {}, 50), {
    name: "NoAnswerError",
    message: /did not answer within 50 ms/,
  });
});

test("the caller's grace scales with the budget it covers", async () => {
  // A flat grace was too tight, and a real portal showed why: the agent measures its deadline with
  // page timers, which a busy or off-screen document runs late, and the drift grows with the wait.
  // Every read on a heavy web client came back as *silence* rather than as the agent's own "no
  // element matched" — which sends the author hunting an engine bug instead of a selector.
  const { callerDeadlineMs } = await import("../dist/webview/rpc.js");
  assert.equal(callerDeadlineMs(0), 2000, "the floor still covers an instantaneous op");
  assert.equal(callerDeadlineMs(5000), 9500);
  assert.equal(callerDeadlineMs(30000), 47000);
  assert.ok(
    callerDeadlineMs(30000) - 30000 > callerDeadlineMs(5000) - 5000,
    "a longer wait earns a longer grace",
  );
});

test("a split answer is reassembled", async () => {
  const { bridge, injected, gen } = bridgeWithAgent();
  const pending = bridge.call("extract", {}, 2000);
  const { id } = orderIn(injected[0]);

  const value = { long: "x".repeat(300) };
  const serialised = JSON.stringify({ aeth: PROTOCOL_VERSION, gen, id, ok: true, value });
  const size = 100;
  const total = Math.ceil(serialised.length / size);
  for (let seq = 0; seq < total; seq += 1) {
    bridge.receive(
      JSON.stringify({
        aeth: PROTOCOL_VERSION,
        gen,
        id,
        seq,
        total,
        part: serialised.slice(seq * size, (seq + 1) * size),
      }),
    );
  }
  assert.deepEqual(await pending, value);
});

test("a split answer that never completes fails rather than hanging", async () => {
  const { bridge, injected, gen } = bridgeWithAgent();
  const pending = bridge.call("extract", {}, 50);
  const { id } = orderIn(injected[0]);

  bridge.receive(JSON.stringify({ aeth: PROTOCOL_VERSION, gen, id, seq: 0, total: 3, part: "{" }));
  await assert.rejects(pending, { name: "NoAnswerError", message: /did not answer/ });
});

test("an answer from a document that has been replaced is dropped, not misattributed", async () => {
  const { bridge, injected, gen } = bridgeWithAgent(1);
  const first = bridge.call("extract", {}, 200);
  const stale = orderIn(injected[0]);

  // The page navigates: the call in flight is a read, so it is failed rather than resolved.
  bridge.invalidate("a new document started loading");
  // `DocumentLostError`, not a plain ActionError: the class is the contract the host retries on.
  await assert.rejects(first, { name: "DocumentLostError", message: /lost its document/ });

  bridge.receive(JSON.stringify({ aeth: PROTOCOL_VERSION, gen: 2, ready: true, url: "http://y/" }));
  const second = bridge.call("extract", {}, 2000);
  const fresh = orderIn(injected[1]);

  // The old document finally answers, reusing nothing but a plausible id shape.
  answer(bridge, 1, stale.id, { ok: true, value: { from: "the dead page" } });
  answer(bridge, 2, fresh.id, { ok: true, value: { from: "the live page" } });

  assert.deepEqual(await second, { from: "the live page" });
});

test("an answer stamped with the wrong generation never resolves its call", async () => {
  const { bridge, injected } = bridgeWithAgent(4);
  const pending = bridge.call("extract", {}, 60);
  const { id } = orderIn(injected[0]);

  answer(bridge, 3, id, { ok: true, value: { stale: true } });
  await assert.rejects(pending, { name: "NoAnswerError", message: /did not answer/ });
});

test("a click that caused the navigation succeeds; a read that lost its page does not", async () => {
  const { bridge } = bridgeWithAgent();
  const clicking = bridge.call("click", { selector: "a" }, 2000);
  const reading = bridge.call("extract", {}, 2000);

  bridge.invalidate("a new document started loading");

  assert.deepEqual(await clicking, {}, "the navigation *is* the click's outcome");
  // At *this* level the read still fails; it is `BridgedHost` that re-issues it on the new
  // document, because only the host knows one has arrived.
  await assert.rejects(reading, { name: "DocumentLostError", message: /lost its document/ });
});

test("a named failure survives the bridge with its code", async () => {
  const { bridge, injected, gen } = bridgeWithAgent();
  const pending = bridge.call("wait_for", { selector: ".x" }, 2000);
  const { id } = orderIn(injected[0]);

  answer(bridge, gen, id, {
    ok: false,
    error: { name: "StepTimeoutError", message: "wait_for timed out", code: "LOGIN_FAILED" },
  });

  await assert.rejects(pending, (error) => {
    assert.equal(error.name, "StepTimeoutError");
    assert.equal(error.code, "LOGIN_FAILED");
    return true;
  });
});

test("a page's own postMessage traffic is ignored, not crashed on", () => {
  const { bridge } = bridgeWithAgent();
  bridge.receive("not json at all");
  bridge.receive(JSON.stringify({ type: "ANALYTICS", payload: 1 }));
  assert.equal(bridge.agentPresent, true, "someone else's message must not disturb the bridge");
});

test("calling before any agent announced itself says exactly that", async () => {
  // `DocumentLostError` (a subclass of ActionError): from the host's point of view this is the same
  // event as an answer lost to a navigation, only noticed a moment earlier — and it is recoverable
  // the same way, by waiting for the next document.
  const bridge = new AgentBridge(() => {});
  await assert.rejects(bridge.call("extract", {}, 100), {
    name: "DocumentLostError",
    message: /no agent is installed on the current document/,
  });
});

test("waiting for readiness resolves on the next announcement", async () => {
  const bridge = new AgentBridge(() => {});
  const waiting = bridge.waitForReady(2000);
  bridge.receive(
    JSON.stringify({ aeth: PROTOCOL_VERSION, gen: 1, ready: true, url: "http://z/" }),
  );
  const ready = await waiting;
  assert.equal(ready.url, "http://z/");
  assert.equal(bridge.currentUrl, "http://z/");
});

test("a view that cannot load the document fails the run as unreachable, not as a bug", async () => {
  // The airplane-mode case, and the one an application must get right: without the view's own
  // signal, the run only learns that no agent announced itself, and reports an engine problem —
  // "internal error" on screen when the phone is simply offline.
  const injected = [];
  const page = {
    load: () => {},
    goBack: () => {},
    goForward: () => {},
    reload: () => {},
    inject: (source) => injected.push(source),
    applySession: () => true,
    destroy: () => {},
  };
  const host = new BridgedHost(page, "/* agent */");
  await host.configure({ persist: false, debug: false, userAgent: undefined }, 1000);

  const navigating = host.navigate("https://example.invalid/", 5000);
  host.onLoadStarted("https://example.invalid/");
  host.onLoadFailed("A server with the specified hostname could not be found.");

  const error = await navigating.then(
    () => null,
    (thrown) => thrown,
  );
  assert.ok(error instanceof NetworkError, `unexpected error: ${error}`);
  assert.equal(describeFailure(error).kind, "unavailable");
  assert.equal(describeFailure(error).retryable, true);
});

test("a load event that follows a failure does not turn it into a success", async () => {
  // The device sequence, and the defect it hid: `react-native-webview` fires `onError` and then
  // `onLoadEnd` for the *same* failed navigation, so the view reports a finished load, the platform
  // shows its own error page, and the agent announces itself on it. The generation advanced, the
  // navigation was declared successful, and the failure the view had just reported was never read —
  // so no Act II network failure could ever reach `unavailable`. Measured on an iPhone against an
  // address that refuses the connection.
  const injected = [];
  const page = recordingPage(injected);
  const host = new BridgedHost(page, "/* agent */");
  await host.configure({ persist: false, debug: false, userAgent: undefined }, 1000);

  const navigating = host.navigate("https://127.0.0.1:1/", 5000);
  host.onLoadStarted("https://127.0.0.1:1/");
  host.onLoadFailed("Could not connect to the server.");
  // The error page: a finished load, a fresh generation, and an agent that announces itself.
  host.onDocumentLoaded("https://127.0.0.1:1/");
  host.onMessage(JSON.stringify({ aeth: 1, gen: 1, ready: true, url: "https://127.0.0.1:1/" }));

  const error = await navigating.then(
    () => null,
    (thrown) => thrown,
  );
  assert.ok(error instanceof NetworkError, `unexpected error: ${error}`);
  assert.equal(describeFailure(error).kind, "unavailable");
  assert.equal(describeFailure(error).retryable, true);
});

test("a later attempt is not condemned by the failure that preceded it", async () => {
  // Written in the order a device produces: the command goes out first, and the view reports back
  // afterwards. `page.load()` is asynchronous, so a verdict cleared only by the view's own
  // `onLoadStart` arrives too late — the waiting loop reads the previous attempt's failure on its
  // first turn and the retry dies instantly, having met nothing.
  const page = recordingPage();
  const host = new BridgedHost(page, "/* agent */");
  await host.configure({ persist: false, debug: false, userAgent: undefined }, 1000);

  host.onLoadStarted("https://example.invalid/");
  host.onLoadFailed("offline");

  const navigating = host.navigate("https://example.invalid/", 2000);
  // A retry after the connection comes back must be able to succeed.
  host.onLoadStarted("https://example.invalid/");
  host.onDocumentLoaded("https://example.invalid/");
  host.onMessage(JSON.stringify({ aeth: 1, gen: 1, ready: true, url: "https://example.invalid/" }));
  assert.equal(await navigating, "https://example.invalid/");
});

test("a view whose last load failed is loaded afresh, never merely reloaded", async () => {
  // A WKWebView whose provisional navigation failed carries no document, and `reload()` on it does
  // nothing at all — which would turn the retry an application offers after "service unavailable"
  // into a silent wait for the deadline.
  const page = recordingPage();
  const host = new BridgedHost(page, "/* agent */");
  await host.configure({ persist: false, debug: false, userAgent: undefined }, 1000);

  host.onLoadStarted("https://127.0.0.1:1/");
  host.onLoadFailed("Could not connect to the server.");

  await host.navigate("https://127.0.0.1:1/", 80).catch(() => {});
  assert.deepEqual(page.calls, ["load:https://127.0.0.1:1/"]);

  // The same URL after a load that *succeeded* is still a reload: nothing changed, so nothing would
  // load, and only asking for one gets a fresh document.
  page.calls.length = 0;
  host.onLoadStarted("https://x.test/");
  host.onDocumentLoaded("https://x.test/");
  host.onMessage(JSON.stringify({ aeth: 1, gen: 1, ready: true, url: "https://x.test/" }));
  await host.navigate("https://x.test/", 80).catch(() => {});
  assert.deepEqual(page.calls, ["reload"]);
});

test("a load that starts and never comes back is unreachable, not an engine bug", async () => {
  // The second symptom the device campaign saw and could not explain: a name that never resolves
  // produces no document and no error before the step's deadline. Blaming the engine there puts
  // "internal error" on screen for a phone on a bad connection.
  const page = recordingPage();
  const host = new BridgedHost(page, "/* agent */");
  await host.configure({ persist: false, debug: false, userAgent: undefined }, 1000);

  const navigating = host.navigate("https://nowhere.invalid/", 120);
  host.onLoadStarted("https://nowhere.invalid/");

  const error = await navigating.then(
    () => null,
    (thrown) => thrown,
  );
  assert.ok(error instanceof TimeoutError, `unexpected error: ${error}`);
  assert.equal(describeFailure(error).kind, "unavailable");
});

test("an operation survives the navigation a redirect causes", async () => {
  // The defect a real phone found and no double could: a login POSTs, the portal answers 302, so
  // the view loads *twice*. The operation in flight lost its document and the run died — meaning
  // no Blueprint could wait for anything after a login, which is most of what Act II does.
  const injected = [];
  const page = {
    load: () => {},
    goBack: () => {},
    goForward: () => {},
    reload: () => {},
    inject: (source) => injected.push(source),
    applySession: () => true,
    destroy: () => {},
  };
  const host = new BridgedHost(page, "/* agent */");
  await host.configure({ persist: false, debug: false, userAgent: undefined }, 1000);

  const announce = (gen, url) =>
    host.onMessage(JSON.stringify({ aeth: 1, gen, ready: true, url }));

  host.onLoadStarted("https://x.test/login");
  host.onDocumentLoaded("https://x.test/login");
  announce(1, "https://x.test/login");

  const reading = host.call("extract", { outputs: {} }, 3000);
  // The host awaits readiness before dispatching, so the order exists one microtask later.
  await tick();

  // The redirect lands while the read is in flight.
  host.onLoadStarted("https://x.test/");
  host.onDocumentLoaded("https://x.test/");
  announce(2, "https://x.test/");
  await tick();

  // The read was re-issued on the new document: answer the second order, not the first.
  const orders = injected
    .filter((source) => source.includes("handle("))
    .map(orderIn)
    .filter((order) => order.op === "extract");
  assert.equal(orders.length, 2, "the operation was not retried on the new document");
  host.onMessage(
    JSON.stringify({ aeth: 1, gen: 2, id: orders[1].id, ok: true, value: { titre: "ok" } }),
  );
  assert.deepEqual(await reading, { titre: "ok" });
});

test("the retry is bounded by the step's deadline, not by the page's patience", async () => {
  // A page that navigates forever must fail on time rather than loop.
  const page = {
    load: () => {},
    goBack: () => {},
    goForward: () => {},
    reload: () => {},
    inject: () => {},
    applySession: () => true,
    destroy: () => {},
  };
  const host = new BridgedHost(page, "/* agent */");
  await host.configure({ persist: false, debug: false, userAgent: undefined }, 1000);
  host.onLoadStarted("https://x.test/");
  host.onDocumentLoaded("https://x.test/");
  host.onMessage(JSON.stringify({ aeth: 1, gen: 1, ready: true, url: "https://x.test/" }));

  const started = Date.now();
  const reading = host.call("extract", { outputs: {} }, 300);
  const churn = setInterval(() => host.onLoadStarted("https://x.test/again"), 30);
  await assert.rejects(reading);
  clearInterval(churn);
  assert.ok(Date.now() - started < 3000, "the retry loop outlived its deadline");
});

/** Let the host's pending microtasks run: dispatching an order goes through `await`. */
function tick() {
  return new Promise((resolve) => setTimeout(resolve, 5));
}

test("a persistent session keeps its view; an isolated one releases it", async () => {
  // What `options.session.persist` has to mean on a device. Destroying the view between runs
  // recreates a WKWebView, and a *session* cookie — the kind a login sets — does not reliably cross
  // that boundary: it lives with the browsing context, not on disk. Found on a phone, where the
  // session was gone at the next run despite `persist: true`.
  const destroyed = [];
  const page = (label) => ({
    load: () => {},
    goBack: () => {},
    goForward: () => {},
    reload: () => {},
    inject: () => {},
    applySession: () => true,
    destroy: () => destroyed.push(label),
  });

  const kept = new BridgedHost(page("persistent"), "/* agent */");
  await kept.configure({ persist: true, debug: false, userAgent: undefined }, 1000);
  await kept.dispose();
  assert.deepEqual(destroyed, [], "a persistent session must not lose its view");

  const released = new BridgedHost(page("isolated"), "/* agent */");
  await released.configure({ persist: false, debug: false, userAgent: undefined }, 1000);
  await released.dispose();
  assert.deepEqual(destroyed, ["isolated"], "an isolated session must release everything");
});

test("a kept view is reloaded, not handed the URL it already shows", async () => {
  // The second half of "a persistent session keeps its view", and the way it first went wrong on a
  // phone: the view survives the run still showing its last page, so the next run's `navigate` to
  // that same page changed nothing — no load started, no document was ever announced, and the run
  // waited out its deadline as an "internal error". Keeping the view only works if navigating back
  // to where it already is means *reload*.
  const calls = [];
  const page = {
    load: (url) => calls.push(`load:${url}`),
    goBack: () => {},
    goForward: () => {},
    reload: () => calls.push("reload"),
    inject: () => {},
    applySession: () => false, // unchanged options + a live view: the component keeps it
    destroy: () => calls.push("destroy"),
  };
  const host = new BridgedHost(page, "/* agent */");
  const session = { persist: true, debug: false, userAgent: undefined };

  await host.configure(session, 1000);
  host.onLoadStarted("https://x.test/");
  host.onDocumentLoaded("https://x.test/");
  host.onMessage(JSON.stringify({ aeth: 1, gen: 1, ready: true, url: "https://x.test/" }));
  await host.dispose();
  assert.ok(!calls.includes("destroy"), "a persistent session must keep its view");

  // Second run, same page.
  await host.configure(session, 1000);
  const navigating = host.navigate("https://x.test/", 2000);
  assert.equal(calls.at(-1), "reload", "the view was not asked to reload");

  host.onLoadStarted("https://x.test/");
  host.onDocumentLoaded("https://x.test/");
  host.onMessage(JSON.stringify({ aeth: 1, gen: 2, ready: true, url: "https://x.test/" }));
  assert.equal(await navigating, "https://x.test/");
});

test("a fragment change keeps the generation, so a call in flight still gets its answer", async () => {
  // The defect a real web client exposed: it sets `location.hash` about a second after its first
  // render. The view reported a finished load, the host called it a new document, the agent
  // reinstalled itself over the operation in flight — and that operation never answered. Every read
  // on that page failed, WebView hidden or visible, with a silence that named nothing.
  const injected = [];
  const page = {
    load: () => {},
    goBack: () => {},
    goForward: () => {},
    reload: () => {},
    inject: (source) => injected.push(source),
    applySession: () => true,
    destroy: () => {},
  };
  const host = new BridgedHost(page, "/* agent */");
  await host.configure({ persist: false, debug: false, userAgent: undefined }, 1000);

  host.onLoadStarted("https://x.test/mail");
  host.onDocumentLoaded("https://x.test/mail");
  host.onMessage(JSON.stringify({ aeth: 1, gen: 1, ready: true, url: "https://x.test/mail" }));

  const reading = host.call("extract", { outputs: {} }, 1000);
  // The call reaches the page through a readiness check, so it is injected a tick later.
  await new Promise((resolve) => setTimeout(resolve, 0));
  const order = orderIn(injected[injected.length - 1]);

  // The client routes to `#1`: same document, new URL.
  host.onDocumentLoaded("https://x.test/mail#1");
  assert.match(
    injected[injected.length - 1],
    /__aetheriusGen = 1;/,
    "a fragment change must not advance the generation",
  );

  // The agent answers the call it is still running, stamped with the generation it was given.
  host.onMessage(
    JSON.stringify({ aeth: PROTOCOL_VERSION, gen: 1, id: order.id, ok: true, value: { lu: 12 } }),
  );
  assert.deepEqual(await reading, { lu: 12 });
});

test("a reload does earn a fresh generation, fragment or not", async () => {
  const injected = [];
  const page = {
    load: () => {},
    goBack: () => {},
    goForward: () => {},
    reload: () => {},
    inject: (source) => injected.push(source),
    applySession: () => true,
    destroy: () => {},
  };
  const host = new BridgedHost(page, "/* agent */");
  await host.configure({ persist: false, debug: false, userAgent: undefined }, 1000);

  host.onLoadStarted("https://x.test/mail#1");
  host.onDocumentLoaded("https://x.test/mail#1");
  assert.match(injected[injected.length - 1], /__aetheriusGen = 1;/);

  // Same URL, fragment included: that is a reload, and the document really is new.
  host.onLoadStarted("https://x.test/mail#1");
  host.onDocumentLoaded("https://x.test/mail#1");
  assert.match(injected[injected.length - 1], /__aetheriusGen = 2;/);
});
