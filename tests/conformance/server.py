"""The fixture HTTP server a ``run`` conformance case talks to (Python half).

A ``run`` case plays a whole Blueprint on both engines and compares what came out. It therefore
needs a server, and it must be the *same* server on both sides — which is why the routes are
declared by the case, in JSON, and each harness implements the same tiny vocabulary. The
TypeScript twin is ``sdks/engine/test/fixture-server.mjs``.

Nothing here reaches the network: it binds an ephemeral port on the loopback interface, and the
harness passes its base URL to the Blueprint as the ``base_url`` input. A corpus that hit a public
endpoint would be a corpus that fails when someone's train enters a tunnel.

Route vocabulary (see conformance/README.md):

    "GET /users":  {"status": 200, "json": [...], "headers": {...}}
    "GET /home":   {"html": "<!doctype html>…"}
    "POST /login": {"status": 302, "body": "", "headers": {"Location": "/home"}}
    "POST /echo":  {"echo": true}
    "GET /csv":    {"body": "Prénom", "charset": "iso-8859-1", "headers": {...}}

``echo`` answers with a JSON description of the request received — method, path, query string,
body and headers. It is what lets a case prove that both engines encode a form body, a query
string and a `Content-Type` identically, without the harness having to know how they should.

``charset`` encodes the literal ``body`` in something other than UTF-8, which is the only way to
serve the mislabelled and non-UTF-8 responses milestone 3-I is about. An unknown label **raises**
rather than falling back: a case that silently served UTF-8 would pass while proving nothing.
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator
from urllib.parse import urlsplit


def _render(route: dict[str, Any], request: dict[str, Any]) -> tuple[int, dict[str, str], bytes]:
    """Turn a declared route into a status, headers and body."""
    if route.get("echo"):
        body = json.dumps(request, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return 200, {"Content-Type": "application/json"}, body

    headers = {str(k): str(v) for k, v in (route.get("headers") or {}).items()}
    if "json" in route:
        body = json.dumps(route["json"], separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    elif "html" in route:
        # A browser needs the right content type to parse a document rather than show its source;
        # `body` stays text/plain so the Act I cases are untouched.
        body = str(route["html"]).encode("utf-8")
        headers.setdefault("Content-Type", "text/html; charset=utf-8")
    else:
        body = str(route.get("body", "")).encode(_charset(route))
        headers.setdefault("Content-Type", "text/plain; charset=utf-8")
    return int(route.get("status", 200)), headers, body


# The twin server (sdks/engine/test/fixture-server.mjs) can only reach these two, and both halves
# must serve the same bytes.
_CHARSETS = {"utf-8": "utf-8", "iso-8859-1": "iso-8859-1", "latin-1": "iso-8859-1"}


def _charset(route: dict[str, Any]) -> str:
    label = str(route.get("charset", "utf-8")).lower()
    codec = _CHARSETS.get(label)
    if codec is None:
        raise ValueError(f"Fixture route charset {label!r} is not supported by both harnesses.")
    return codec


def _handler_class(routes: dict[str, Any]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_: Any) -> None:
            """Silence: a conformance run should print its own failures, not an access log."""

        def _serve(self) -> None:
            split = urlsplit(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            request = {
                "method": self.command,
                "path": split.path,
                "query": split.query,
                "body": raw.decode("utf-8", errors="replace"),
                "headers": {k.lower(): v for k, v in self.headers.items()},
            }

            route = routes.get(f"{self.command} {split.path}")
            if route is None:
                status, headers, body = 404, {"Content-Type": "text/plain"}, b"no route"
            else:
                status, headers, body = _render(route, request)

            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = _serve
        do_POST = _serve
        do_PUT = _serve
        do_PATCH = _serve
        do_DELETE = _serve

    return Handler


@contextmanager
def fixture_server(routes: dict[str, Any]) -> Iterator[str]:
    """Serve *routes* on the loopback interface; yields the base URL, stops on exit."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_class(routes))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
