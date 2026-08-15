/**
 * Act I on `fetch`: encodings, retries, timeouts, cookies and authentication.
 *
 * `fetch` is injected rather than mocked at module level — it is a parameter of the engine for
 * exactly this reason. What the assertions look at is the *request that would go out*, because
 * that is where the two engines could silently disagree: a form body encoded one character
 * differently raises nothing, it just gets a different answer from the server.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { VectorClient, BasicAuth, BearerAuth, CasFormLogin, CookieAuth } from "../dist/index.js";
import {
  ActionError,
  NetworkError,
  StatusAssertionError,
  TimeoutError,
} from "../dist/errors.js";
import { RunEngine } from "../dist/runtime/engine.js";

/**
 * A response shaped like the slice of `fetch` the engine reads.
 *
 * `bytes` opts into the raw-body surface a `from: "text"` extraction needs; leaving it out is how a
 * host without `arrayBuffer()` is reproduced, which is a case the engine has to name rather than
 * decode as UTF-8 behind the author's back.
 */
function reply({ status = 200, body = "", headers = {}, setCookie, url, bytes } = {}) {
  const map = new Map(Object.entries(headers).map(([name, value]) => [name.toLowerCase(), value]));
  const read = { text: 0, arrayBuffer: 0 };
  const response = {
    status,
    ...(url !== undefined ? { url } : {}),
    headers: {
      get: (name) => map.get(name.toLowerCase()) ?? null,
      forEach: (callback) => map.forEach((value, name) => callback(value, name)),
      ...(setCookie !== undefined ? { getSetCookie: () => setCookie } : {}),
    },
    text: async () => {
      read.text += 1;
      return body;
    },
    ...(bytes !== undefined
      ? {
          arrayBuffer: async () => {
            read.arrayBuffer += 1;
            return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
          },
        }
      : {}),
    read,
  };
  return response;
}

/** Records every call and answers with whatever *handler* returns (an Error is thrown). */
function fakeFetch(handler) {
  const calls = [];
  const fetch = async (url, init = {}) => {
    calls.push({ url, ...init });
    const answer = await handler({ url, ...init }, calls.length);
    if (answer instanceof Error) throw answer;
    return answer ?? reply();
  };
  return { fetch, calls };
}

const blueprint = (step, extra = {}) => ({
  aetherius: "1.0",
  name: "vector.demo",
  act: "vector",
  steps: [{ id: "call", action: "http.request", ...step }],
  ...extra,
});

async function run(step, handler, extra = {}, options = {}) {
  const { fetch, calls } = fakeFetch(handler);
  const result = await new RunEngine().run(blueprint(step, extra), {
    ...options,
    fetch,
    sinks: [],
  });
  return { result, calls };
}

// ── Encodings ────────────────────────────────────────────────────────────────

test("params replace the URL query and follow Python's quote_plus", async () => {
  const { calls } = await run(
    {
      url: "https://api.test/path?dropped=1#frag",
      params: { q: "a b~c*d", n: ["1", "2"], flag: true, none: null },
    },
    () => reply(),
  );
  assert.equal(calls[0].url, "https://api.test/path?q=a+b~c%2Ad&n=1&n=2&flag=true&none=#frag");
});

test("a form body is urlencoded like httpx, booleans and nulls included", async () => {
  const { calls } = await run(
    {
      method: "POST",
      url: "https://api.test/login",
      form: { user: "é@x", flag: true, off: false, missing: null, ids: [1, 2] },
    },
    () => reply(),
  );
  assert.equal(calls[0].method, "POST");
  assert.equal(calls[0].body, "user=%C3%A9%40x&flag=true&off=false&missing=&ids=1&ids=2");
  assert.equal(calls[0].headers["Content-Type"], "application/x-www-form-urlencoded");
});

test("a json body is compact and keeps non-ASCII characters", async () => {
  const { calls } = await run(
    { method: "POST", url: "https://api.test/items", json: { a: true, b: null, d: "é" } },
    () => reply(),
  );
  assert.equal(calls[0].body, '{"a":true,"b":null,"d":"é"}');
  assert.equal(calls[0].headers["Content-Type"], "application/json");
});

test("the Blueprint's own Content-Type wins over the encoder's default", async () => {
  const { calls } = await run(
    {
      method: "POST",
      url: "https://api.test/login",
      headers: { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" },
      form: { a: "1" },
    },
    () => reply(),
  );
  assert.equal(
    calls[0].headers["Content-Type"],
    "application/x-www-form-urlencoded; charset=UTF-8",
  );
});

test("a null json renders as absent, so it does not clash with a form", async () => {
  const { calls, result } = await run(
    { method: "POST", url: "https://api.test/x", json: "{{ none }}", form: { a: "1" } },
    () => reply(),
  );
  assert.equal(result.status, "success");
  assert.equal(calls[0].body, "a=1");
});

test("json and form together are refused, before anything is sent", async () => {
  const { calls, result } = await run(
    { method: "POST", url: "https://api.test/x", json: { a: 1 }, form: { a: "1" } },
    () => reply(),
  );
  assert.equal(result.status, "failed");
  assert.match(result.error, /Cannot set both 'json' and 'form'/);
  assert.equal(calls.length, 0);
});

// ── Response, assertions and extraction ──────────────────────────────────────

test("the step publishes the status and headers, plus its extractions", async () => {
  const { result } = await run(
    {
      url: "https://api.test/users",
      expect: { status: 200 },
      extract: { names: { from: "json", path: "$[*].name" } },
    },
    () => reply({ body: '[{"name": "Ada"}, {"name": "Alan"}]', headers: { "X-Kind": "json" } }),
  );
  assert.deepEqual(result.step_results[0].outputs, {
    status_code: 200,
    headers: { "x-kind": "json" },
    names: ["Ada", "Alan"],
  });
});

test("HTML extraction runs on the same response body", async () => {
  const { result } = await run(
    {
      url: "https://api.test/page",
      extract: { quote: { from: "html", selector: "span.text::text" } },
    },
    () => reply({ body: "<div><span class='text'>Hello</span></div>" }),
  );
  assert.deepEqual(result.step_results[0].outputs.quote, ["Hello"]);
});

test("a violated expect.status fails the run with the status in the message", async () => {
  const { result } = await run(
    { url: "https://api.test/x", expect: { status: 200 } },
    () => reply({ status: 503, body: "upstream down" }),
  );
  assert.equal(result.status, "failed");
  assert.equal(result.error, "Expected HTTP 200, got 503 — https://api.test/x\nupstream down");
});

// ── Retries ──────────────────────────────────────────────────────────────────

test("a transport failure is retried, then the run succeeds", async () => {
  const { result, calls } = await run(
    { url: "https://api.test/x" },
    (_request, attempt) => (attempt === 1 ? new Error("ECONNRESET") : reply({ body: "ok" })),
    { options: { retries: { max: 2, backoff: "none" } } },
  );
  assert.equal(result.status, "success");
  assert.equal(calls.length, 2);
});

test("exhausted retries raise the last transport error, not a retry wrapper", async () => {
  const { result, calls } = await run(
    { url: "https://api.test/x" },
    () => new Error("ECONNREFUSED"),
    { options: { retries: { max: 2, backoff: "none" } } },
  );
  assert.equal(calls.length, 3, "max + 1 attempts");
  assert.equal(result.status, "failed");
  assert.equal(result.error, "Transport error: ECONNREFUSED");
});

test("retries.max = 0 disables retrying entirely", async () => {
  const { calls } = await run({ url: "https://api.test/x" }, () => new Error("nope"), {
    options: { retries: { max: 0, backoff: "exponential" } },
  });
  assert.equal(calls.length, 1);
});

test("a status code is an answer, never a retry", async () => {
  const { calls } = await run(
    { url: "https://api.test/x", expect: { status: 200 } },
    () => reply({ status: 500 }),
    { options: { retries: { max: 3, backoff: "none" } } },
  );
  assert.equal(calls.length, 1);
});

// ── Timeout ──────────────────────────────────────────────────────────────────

test("a request that outlives options.timeout_ms is aborted and reported as a timeout", async () => {
  const { result, calls } = await run(
    { url: "https://api.test/slow" },
    ({ signal }) =>
      new Promise((_resolve, reject) => {
        const poll = setInterval(() => {
          if (signal?.aborted === true) {
            clearInterval(poll);
            reject(new Error("aborted"));
          }
        }, 1);
      }),
    { options: { timeout_ms: 20 } },
  );
  assert.equal(calls.length, 1);
  assert.equal(result.status, "failed");
  assert.equal(result.error, "Request timed out: GET https://api.test/slow");
});

// ── Cookies ──────────────────────────────────────────────────────────────────

test("a captured Set-Cookie comes back on the next request of the run", async () => {
  const seen = [];
  const { fetch } = fakeFetch((request, attempt) => {
    seen.push(request.headers["Cookie"]);
    return attempt === 1 ? reply({ setCookie: ["SESSION=abc; Path=/; HttpOnly"] }) : reply();
  });
  const client = new VectorClient({ fetch });
  await client.request({ url: "https://api.test/login" });
  await client.request({ url: "https://api.test/me" });

  assert.deepEqual(seen, [undefined, "SESSION=abc"]);
});

test("a host that does not expose Set-Cookie makes the jar send nothing", async () => {
  const seen = [];
  const { fetch } = fakeFetch((request) => {
    seen.push(request.headers["Cookie"]);
    // No `getSetCookie`: what a React Native runtime looks like. The platform store does the work.
    return reply({ headers: { "set-cookie": "SESSION=abc" } });
  });
  const client = new VectorClient({ fetch });
  await client.request({ url: "https://api.test/login" });
  await client.request({ url: "https://api.test/me" });

  assert.deepEqual(seen, [undefined, undefined], "never a cookie the platform would send too");
});

test("a cleared cookie is dropped rather than replayed", async () => {
  const seen = [];
  const { fetch } = fakeFetch((request, attempt) => {
    seen.push(request.headers["Cookie"]);
    if (attempt === 1) return reply({ setCookie: ["SESSION=abc"] });
    if (attempt === 2) return reply({ setCookie: ["SESSION=; Max-Age=0"] });
    return reply();
  });
  const client = new VectorClient({ fetch });
  await client.request({ url: "https://api.test/login" });
  await client.request({ url: "https://api.test/logout" });
  await client.request({ url: "https://api.test/me" });

  assert.deepEqual(seen, [undefined, "SESSION=abc", undefined]);
});

// ── Authentication ───────────────────────────────────────────────────────────

test("BearerAuth sets the Authorization header on every request", async () => {
  const { fetch, calls } = fakeFetch(() => reply());
  const client = new VectorClient({ fetch, auth: new BearerAuth("t0ken") });
  await client.setup();
  await client.request({ url: "https://api.test/x" });
  assert.equal(calls[0].headers["Authorization"], "Bearer t0ken");
});

test("BasicAuth encodes UTF-8 credentials the way base64 requires", async () => {
  const { fetch, calls } = fakeFetch(() => reply());
  const client = new VectorClient({ fetch, auth: new BasicAuth("aladdin", "opé:sésame") });
  await client.setup();
  await client.request({ url: "https://api.test/x" });
  assert.equal(
    calls[0].headers["Authorization"],
    `Basic ${Buffer.from("aladdin:opé:sésame", "utf8").toString("base64")}`,
  );
});

test("CookieAuth seeds the jar, so the cookies travel as a header", async () => {
  const { fetch, calls } = fakeFetch(() => reply());
  const client = new VectorClient({ fetch, auth: new CookieAuth({ a: "1", b: "2" }) });
  await client.setup();
  await client.request({ url: "https://api.test/x" });
  assert.equal(calls[0].headers["Cookie"], "a=1; b=2");
});

test("CasFormLogin carries the page's hidden fields back with the credentials", async () => {
  const page =
    "<html><body><form method='post'>" +
    "<input type='hidden' name='execution' value='e1s1'>" +
    "<input type='hidden' name='_eventId' value='submit'>" +
    "<input type='hidden' value='no-name-ignored'>" +
    "<input type='text' name='username'></form></body></html>";

  const { fetch, calls } = fakeFetch((request, attempt) =>
    attempt === 1 ? reply({ body: page }) : reply({ setCookie: ["TGC=ticket"] }),
  );
  const client = new VectorClient({
    fetch,
    auth: new CasFormLogin("https://cas.test/login", "ada", "p@ss word"),
  });
  await client.setup();
  await client.request({ url: "https://portal.test/me" });

  assert.equal(calls[1].method, "POST");
  assert.equal(
    calls[1].body,
    "execution=e1s1&_eventId=submit&username=ada&password=p%40ss+word",
  );
  assert.equal(calls[2].headers["Cookie"], "TGC=ticket", "the session reached the next request");
});

test("a login page that answers with an error fails loudly, with a typed error", async () => {
  const { fetch } = fakeFetch(() => reply({ status: 500, body: "cas down" }));
  const client = new VectorClient({
    fetch,
    auth: new CasFormLogin("https://cas.test/login", "ada", "secret"),
  });
  await assert.rejects(() => client.setup(), StatusAssertionError);
});

// ── Typed errors ─────────────────────────────────────────────────────────────

test("each failure mode carries its own error class", async () => {
  const client = (handler) => new VectorClient({ fetch: fakeFetch(handler).fetch });

  await assert.rejects(
    () => client(() => new Error("down")).request({ url: "https://api.test/x" }),
    NetworkError,
  );
  await assert.rejects(
    () =>
      client(() => reply({ status: 404 })).request({
        url: "https://api.test/x",
        expectedStatus: 200,
      }),
    StatusAssertionError,
  );
  await assert.rejects(
    () =>
      client(() => reply()).request({ url: "https://api.test/x", json: { a: 1 }, form: { b: 2 } }),
    ActionError,
  );
  assert.ok(new TimeoutError("x") instanceof NetworkError, "a timeout is retryable like a transport error");
});

// ── Le corps en texte ────────────────────────────────────────────────────────

test("an extraction from: text reads the raw body and decodes it per the response charset", async () => {
  const bytes = new Uint8Array(Buffer.from("BEGIN:VCALENDAR\r\nSUMMARY:Noël\r\n", "latin1"));
  const answer = reply({
    headers: { "Content-Type": "text/calendar; charset=iso-8859-1" },
    body: "never read",
    bytes,
  });
  const { result } = await run(
    { url: "https://cal.test/ics", extract: { ics: { from: "text" } } },
    () => answer,
    { outputs: { ics: "{{ steps.call.ics }}" } },
  );

  assert.equal(result.status, "success");
  assert.equal(result.outputs.ics, "BEGIN:VCALENDAR\r\nSUMMARY:Noël\r\n");
  // The body is read once, as bytes: reading it twice is not allowed by any host.
  assert.deepEqual(answer.read, { text: 0, arrayBuffer: 1 });
});

test("a step without a text extraction keeps reading the body as text", async () => {
  // The whole point of deciding before the request: on a device the bytes go through a base64
  // bridge, and no request that does not need them should pay for it.
  const answer = reply({ body: '{"id": 1}', bytes: new Uint8Array([0x7b, 0x7d]) });
  const { result } = await run(
    { url: "https://api.test/x", extract: { id: { from: "json", path: "$.id" } } },
    () => answer,
    { outputs: { id: "{{ steps.call.id | first }}" } },
  );

  assert.equal(result.outputs.id, 1);
  assert.deepEqual(answer.read, { text: 1, arrayBuffer: 0 });
});

test("a host whose response cannot hand over bytes says so, and is not a network failure", async () => {
  const { result } = await run(
    { url: "https://cal.test/ics", extract: { ics: { from: "text" } } },
    () => reply({ body: "BEGIN:VCALENDAR" }),
  );

  assert.equal(result.status, "failed");
  assert.match(result.error, /arrayBuffer\(\)/);
  assert.match(result.error, /from: "text"/);
  assert.doesNotMatch(result.error, /Transport error/);
});

test("the status assertion still reads the UTF-8 body in bytes mode", async () => {
  // `expect`, JSON and HTML see the same string either way; only the text dialect re-reads.
  const { result } = await run(
    {
      url: "https://cal.test/ics",
      expect: { status: 200 },
      extract: { ics: { from: "text" } },
    },
    () => reply({ status: 500, bytes: new Uint8Array(Buffer.from("boom é", "utf8")) }),
  );

  assert.equal(result.status, "failed");
  assert.match(result.error, /Expected HTTP 200, got 500/);
  assert.match(result.error, /boom é/);
});
