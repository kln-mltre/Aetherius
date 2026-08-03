/**
 * The fixture HTTP server a `run` conformance case talks to (TypeScript half).
 *
 * Twin of `tests/conformance/server.py`: same route vocabulary, same answers, because a `run` case
 * is only meaningful if both engines faced the same server. Binds an ephemeral loopback port — a
 * corpus that reached a public endpoint would fail for reasons that have nothing to do with the
 * engines.
 *
 * Route vocabulary (see conformance/README.md):
 *
 *     "GET /users":  { status: 200, json: [...], headers: {...} }
 *     "GET /home":   { html: "<!doctype html>…" }
 *     "POST /login": { status: 302, body: "", headers: { Location: "/home" } }
 *     "POST /echo":  { echo: true }
 */

import { createServer } from "node:http";

function render(route, request) {
  if (route.echo === true) {
    return {
      status: 200,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    };
  }

  const headers = { ...(route.headers ?? {}) };
  let body;
  if (Object.prototype.hasOwnProperty.call(route, "json")) {
    body = JSON.stringify(route.json);
    setDefault(headers, "Content-Type", "application/json");
  } else if (Object.prototype.hasOwnProperty.call(route, "html")) {
    // A browser needs the right content type to parse a document rather than show its source;
    // `body` stays text/plain so the Act I cases are untouched.
    body = String(route.html);
    setDefault(headers, "Content-Type", "text/html; charset=utf-8");
  } else {
    body = String(route.body ?? "");
    setDefault(headers, "Content-Type", "text/plain; charset=utf-8");
  }
  return { status: route.status ?? 200, headers, body };
}

function setDefault(headers, name, value) {
  const wanted = name.toLowerCase();
  if (!Object.keys(headers).some((key) => key.toLowerCase() === wanted)) headers[name] = value;
}

async function readBody(incoming) {
  const chunks = [];
  for await (const chunk of incoming) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

/** Serve *routes* on the loopback interface; resolves to the base URL and a `close()`. */
export async function fixtureServer(routes) {
  const server = createServer((incoming, outgoing) => {
    void (async () => {
      const url = new URL(incoming.url, "http://127.0.0.1");
      const request = {
        method: incoming.method,
        path: url.pathname,
        query: url.search.startsWith("?") ? url.search.slice(1) : url.search,
        body: await readBody(incoming),
        headers: { ...incoming.headers },
      };

      const route = routes[`${incoming.method} ${url.pathname}`];
      const answer =
        route === undefined
          ? { status: 404, headers: { "Content-Type": "text/plain" }, body: "no route" }
          : render(route, request);

      outgoing.writeHead(answer.status, {
        ...answer.headers,
        "Content-Length": Buffer.byteLength(answer.body),
      });
      outgoing.end(answer.body);
    })();
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  return {
    baseUrl: `http://127.0.0.1:${port}`,
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}
