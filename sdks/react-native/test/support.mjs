/**
 * Shared scaffolding for the Act II tests: a tiny HTML server, and a host wired to jsdom.
 *
 * Every test here drives the *production* path — the real `BridgedHost`, the real `AgentBridge`,
 * the real bundled agent — against a DOM rather than a WebView. What the double replaces is the
 * platform, never the logic.
 */

import { createServer } from "node:http";

import { createDomHost } from "./dom-host.mjs";

/** Serve *pages* (path -> HTML, or path -> handler) on an ephemeral loopback port. */
export async function htmlServer(pages) {
  const server = createServer((incoming, outgoing) => {
    void (async () => {
      const url = new URL(incoming.url, "http://127.0.0.1");
      const route = pages[url.pathname];
      if (route === undefined) {
        outgoing.writeHead(404, { "Content-Type": "text/plain" });
        outgoing.end("no page");
        return;
      }
      const chunks = [];
      for await (const chunk of incoming) chunks.push(chunk);
      const body = Buffer.concat(chunks).toString("utf8");

      const answer =
        typeof route === "function"
          ? route({ method: incoming.method, query: url.search.slice(1), body, headers: incoming.headers })
          : { body: route };
      outgoing.writeHead(answer.status ?? 200, {
        "Content-Type": "text/html; charset=utf-8",
        ...(answer.headers ?? {}),
      });
      outgoing.end(answer.body ?? "");
    })();
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  return {
    baseUrl: `http://127.0.0.1:${server.address().port}`,
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}

const DEFAULT_SESSION = { persist: false, debug: false, userAgent: undefined };

/** A host that has already loaded *path*, plus the page and the server it talks to. */
export async function openPage(pages, path = "/", session = DEFAULT_SESSION) {
  const server = await htmlServer(pages);
  const { host, page } = createDomHost();
  await host.configure(session, 5000);
  await host.navigate(`${server.baseUrl}${path}`, 5000);
  return {
    host,
    page,
    baseUrl: server.baseUrl,
    async close() {
      await host.dispose();
      await server.close();
    },
  };
}
