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
    "POST /login": {"status": 302, "body": "", "headers": {"Location": "/home"}}
    "POST /echo":  {"echo": true}

``echo`` answers with a JSON description of the request received — method, path, query string,
body and headers. It is what lets a case prove that both engines encode a form body, a query
string and a `Content-Type` identically, without the harness having to know how they should.
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
    else:
        body = str(route.get("body", "")).encode("utf-8")
        headers.setdefault("Content-Type", "text/plain; charset=utf-8")
    return int(route.get("status", 200)), headers, body


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
