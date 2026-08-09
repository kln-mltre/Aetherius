/**
 * A `WebViewHost` backed by jsdom — how Act II is tested, and replayed by the conformance corpus,
 * without a phone.
 *
 * It is deliberately *not* a reimplementation of the driver: it supplies the five calls of
 * `PageControl` and lets the real `BridgedHost`, the real `AgentBridge` and the real injected agent
 * do everything else. What runs here is the production lifecycle — generation tokens, ready state,
 * correlated answers, chunk reassembly — against a DOM instead of a WebView.
 *
 * Three things a browser provides and jsdom does not, supplied here rather than branched around in
 * the agent (the agent must stay single-path: a real WebView always has all three):
 *
 *   - **layout**: `getBoundingClientRect` and `innerText`. Without them every element would read as
 *     invisible and every text read would come back empty;
 *   - **navigation**: jsdom fires `submit` and `click` but never follows them. The glue below turns
 *     them into a request, exactly as a browser would, cookies included;
 *   - **the React Native bridge**: `window.ReactNativeWebView.postMessage`.
 */

import { JSDOM } from "jsdom";

import { CookieJar } from "@aetherius/engine";

import { BridgedHost } from "../dist/webview/bridged-host.js";
import { AGENT_SOURCE } from "../dist/generated/agent-source.js";

/** Tags whose content a browser lays out on its own line, for the `innerText` approximation. */
const BLOCK = new Set([
  "address", "article", "aside", "blockquote", "br", "div", "dd", "dl", "dt", "fieldset",
  "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr",
  "li", "main", "nav", "ol", "p", "pre", "section", "table", "tbody", "td", "tfoot", "th", "thead",
  "tr", "ul",
]);

const MAX_REDIRECTS = 20;

function isHidden(window, element) {
  const style = window.getComputedStyle(element);
  return style.display === "none" || style.visibility === "hidden" || style.visibility === "collapse";
}

/** Rendered text, near enough to a browser's `innerText` for the markup a Blueprint reads. */
function renderedText(window, node) {
  if (node.nodeType === 3) return node.data;
  if (node.nodeType !== 1) return "";
  const tag = node.tagName.toLowerCase();
  if (tag === "script" || tag === "style" || tag === "head") return "";
  if (isHidden(window, node)) return "";
  if (tag === "br") return "\n";

  let out = "";
  for (const child of node.childNodes) out += renderedText(window, child);
  return BLOCK.has(tag) ? `\n${out}\n` : out;
}

function installLayout(window) {
  const { Element, HTMLElement } = window;

  Object.defineProperty(HTMLElement.prototype, "innerText", {
    configurable: true,
    get() {
      return renderedText(window, this)
        .replace(/[ \t\r\f]+/g, " ")
        .replace(/ ?\n ?/g, "\n")
        .replace(/\n{2,}/g, "\n")
        .trim();
    },
  });

  // A fixed box, so the agent's stability check sees two identical rects rather than an element
  // that never stops moving. Hidden elements get an empty box, which is what makes them invisible.
  Element.prototype.getBoundingClientRect = function getBoundingClientRect() {
    const empty = { x: 0, y: 0, width: 0, height: 0, top: 0, left: 0, right: 0, bottom: 0 };
    if (!this.isConnected || isHidden(window, this)) return empty;
    return { x: 0, y: 0, width: 120, height: 24, top: 0, left: 0, right: 120, bottom: 24 };
  };

  Element.prototype.scrollIntoView = function scrollIntoView() {};
  window.scrollBy = function scrollBy() {};
}

function formRequest(window, form, submitter) {
  const method = (form.getAttribute("method") ?? "GET").toUpperCase();
  const action = form.getAttribute("action");
  const url = new window.URL(action === null || action === "" ? window.location.href : action,
    window.location.href);

  const pairs = [];
  for (const field of form.elements) {
    const name = field.getAttribute?.("name");
    if (!name || field.disabled) continue;
    const type = (field.getAttribute("type") ?? "").toLowerCase();
    if (type === "submit" || type === "button" || type === "reset" || type === "image") continue;
    if ((type === "checkbox" || type === "radio") && !field.checked) continue;
    pairs.push([name, field.value ?? ""]);
  }
  // The submitter's own name/value is part of the submission, and portals read it to tell two
  // buttons of the same form apart.
  const submitterName = submitter?.getAttribute?.("name");
  if (submitterName) pairs.push([submitterName, submitter.value ?? ""]);

  const body = new URLSearchParams(pairs).toString();
  if (method === "GET") {
    url.search = body;
    return { method, url: url.href, body: undefined };
  }
  return { method, url: url.href, body };
}

export class DomPage {
  #host;
  #fetch;
  #jar = new CookieJar();
  #dom;
  #history = [];
  #cursor = -1;
  #session = { persist: false, debug: false, userAgent: undefined };
  #configured = false;
  #destroyed = false;

  constructor(fetchImpl) {
    this.#fetch = fetchImpl ?? globalThis.fetch;
  }

  attach(host) {
    this.#host = host;
  }

  /** The session options the last `applySession` accepted — what a test asserts on. */
  get session() {
    return this.#session;
  }

  /** The current jsdom window, for tests that want to poke at the DOM directly. */
  get window() {
    return this.#dom?.window;
  }

  // -- PageControl -------------------------------------------------------------------------

  load(url) {
    this.#history = this.#history.slice(0, this.#cursor + 1);
    this.#history.push(url);
    this.#cursor = this.#history.length - 1;
    void this.#go(url, { method: "GET" });
  }

  goBack() {
    if (this.#cursor <= 0) return;
    this.#cursor -= 1;
    void this.#go(this.#history[this.#cursor], { method: "GET" });
  }

  goForward() {
    if (this.#cursor >= this.#history.length - 1) return;
    this.#cursor += 1;
    void this.#go(this.#history[this.#cursor], { method: "GET" });
  }

  reload() {
    if (this.#cursor < 0) return;
    void this.#go(this.#history[this.#cursor], { method: "GET" });
  }

  inject(source) {
    // `window.eval` is jsdom's way in from the outside, and stands for the platform's
    // `injectJavaScript`. The agent itself builds no code — that is what its own guard checks.
    this.#dom?.window.eval(source);
  }

  applySession(config) {
    const same =
      this.#configured &&
      !this.#destroyed &&
      this.#session.persist === config.persist &&
      this.#session.debug === config.debug &&
      this.#session.userAgent === config.userAgent;
    this.#session = config;
    this.#configured = true;
    // A released page is revived here, exactly as the component recreates its view: the page's
    // lifetime is the component's, not the run's.
    this.#destroyed = false;
    if (same) return false;
    // Recreating the view drops the store when the session is isolated — the observable difference
    // between `persist: true` and `persist: false` on a device.
    if (!config.persist) this.#jar = new CookieJar();
    this.#closeDocument();
    return true;
  }

  /** Release the document (and, for an isolated session, its store). The page stays reusable. */
  destroy() {
    this.#destroyed = true;
    if (!this.#session.persist) this.#jar = new CookieJar();
    this.#history = [];
    this.#cursor = -1;
    this.#closeDocument();
  }

  // -- navigation --------------------------------------------------------------------------

  async #go(url, request) {
    if (this.#destroyed) return;
    this.#host.onLoadStarted(url);

    let response;
    let current = url;
    try {
      response = await this.#request(current, request);
      current = response.url;
    } catch (error) {
      // **The exact sequence a device produces**, and it is not obvious: `react-native-webview`
      // fires `onError` and then `onLoadEnd` for the same failed navigation, in the same tick
      // (`WebViewShared.onLoadingError`). So the view reports the failure *and* a finished load, the
      // platform shows its own error page, and the agent installs itself on it like on any other
      // document. Reproducing only the load event — which this double used to do — hid the defect
      // where the corpus could never find it: the host declared the navigation a success.
      const description = `${String(error.message)} (${url})`;
      this.#host.onLoadFailed(description);
      this.#mount(`<html><body data-load-error="${description}"></body></html>`, url);
      this.#host.onDocumentLoaded(url);
      return;
    }

    this.#mount(response.body, current);
    if (this.#cursor >= 0) this.#history[this.#cursor] = current;
    this.#host.onDocumentLoaded(current);
  }

  /**
   * Follow redirects by hand, capturing cookies at each hop.
   *
   * `redirect: "follow"` would hide the intermediate responses, and a session cookie set by a 302 —
   * the shape of every form login — would be lost. A real WebView keeps it, so this must too.
   */
  async #request(url, { method, body }) {
    let target = url;
    let verb = method;
    let payload = body;

    for (let hop = 0; hop <= MAX_REDIRECTS; hop += 1) {
      const headers = { Accept: "text/html,*/*" };
      const cookie = this.#jar.header();
      if (cookie !== undefined) headers["Cookie"] = cookie;
      if (payload !== undefined) headers["Content-Type"] = "application/x-www-form-urlencoded";
      if (this.#session.userAgent !== undefined) headers["User-Agent"] = this.#session.userAgent;

      const response = await this.#fetch(target, {
        method: verb,
        headers,
        redirect: "manual",
        ...(payload !== undefined ? { body: payload } : {}),
      });
      this.#jar.capture(response.headers);

      const location = response.headers.get("location");
      if (response.status >= 300 && response.status < 400 && location !== null) {
        target = new URL(location, target).href;
        // 303, and 301/302 after a POST, become a GET — the rule every browser follows.
        verb = "GET";
        payload = undefined;
        continue;
      }
      return { url: target, body: await response.text() };
    }
    throw new Error(`too many redirects starting at ${url}`);
  }

  #mount(html, url) {
    this.#closeDocument();
    const dom = new JSDOM(html, { url, runScripts: "outside-only", pretendToBeVisual: true });
    this.#dom = dom;
    const { window } = dom;

    installLayout(window);
    window.ReactNativeWebView = {
      postMessage: (payload) => {
        this.#host.onMessage(payload);
      },
    };

    window.addEventListener(
      "submit",
      (event) => {
        event.preventDefault();
        const { method, url: action, body } = formRequest(window, event.target, event.submitter);
        this.#history = this.#history.slice(0, this.#cursor + 1);
        this.#history.push(action);
        this.#cursor = this.#history.length - 1;
        void this.#go(action, { method, body });
      },
      true,
    );

    window.addEventListener(
      "click",
      (event) => {
        const anchor = event.target?.closest?.("a[href]");
        const href = anchor?.getAttribute("href");
        if (!href || href.startsWith("javascript:") || href.startsWith("#")) return;
        event.preventDefault();
        this.load(new window.URL(href, window.location.href).href);
      },
      true,
    );
  }

  #closeDocument() {
    this.#dom?.window.close();
    this.#dom = undefined;
  }
}

/** A `BridgedHost` driving a jsdom page: what a test or the conformance runner registers. */
export function createDomHost(fetchImpl) {
  const page = new DomPage(fetchImpl);
  const host = new BridgedHost(page, AGENT_SOURCE);
  page.attach(host);
  return { host, page };
}
