"""ProxySpec: one proxy endpoint, described once and rendered per engine.

httpx (Vector) wants a URL string; Playwright (Continuum) wants a ``{server, username, password}``
dict. Credentials are kept out of logs via :meth:`ProxySpec.redacted`.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, unquote, urlsplit

from ..core.errors import BlueprintValidationError

# Schemes we support across both engines. HTTP/HTTPS need no extra dependency; SOCKS5 rides the
# optional [network] extra (socksio for httpx, bundled for curl_cffi and Playwright).
_SCHEMES = frozenset({"http", "https", "socks5"})


@dataclass(frozen=True, slots=True)
class ProxySpec:
    """A single proxy endpoint. ``scheme`` is one of ``http`` / ``https`` / ``socks5``."""

    scheme: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None

    @property
    def server_url(self) -> str:
        """``scheme://host:port`` without credentials — the form Playwright's ``server`` expects."""
        return f"{self.scheme}://{self.host}:{self.port}"

    def for_httpx(self) -> str:
        """Full proxy URL (credentials inlined) for ``httpx.Client(proxy=...)``."""
        if self.username is None and self.password is None:
            return self.server_url
        # Percent-encode credentials so a ':' or '@' in a password cannot corrupt the URL.
        user = quote(self.username or "", safe="")
        password = quote(self.password or "", safe="")
        return f"{self.scheme}://{user}:{password}@{self.host}:{self.port}"

    def for_playwright(self) -> dict[str, str]:
        """``{server, username, password}`` for Playwright's ``proxy=`` option.

        Playwright expects the raw (unencoded) credentials as separate fields, and the server URL
        without them.
        """
        proxy: dict[str, str] = {"server": self.server_url}
        if self.username is not None:
            proxy["username"] = self.username
        if self.password is not None:
            proxy["password"] = self.password
        return proxy

    def redacted(self) -> str:
        """A log-safe representation with credentials masked."""
        if self.username is None and self.password is None:
            return self.server_url
        return f"{self.scheme}://***@{self.host}:{self.port}"


def parse_proxy(url: str) -> ProxySpec:
    """Parse a proxy URL (``scheme://user:pass@host:port``) into a :class:`ProxySpec`.

    Raises:
        BlueprintValidationError: on an unknown scheme, a missing host, or a missing/invalid port.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in _SCHEMES:
        raise BlueprintValidationError(
            f"Unsupported proxy scheme {parts.scheme!r} (supported: {sorted(_SCHEMES)})."
        )
    if not parts.hostname:
        raise BlueprintValidationError(f"Proxy URL {url!r} is missing a host.")
    if parts.port is None:
        raise BlueprintValidationError(
            f"Proxy URL {url!r} is missing a port (expected scheme://host:port)."
        )
    # urlsplit already percent-decodes nothing in userinfo, so decode explicitly.
    username = unquote(parts.username) if parts.username else None
    password = unquote(parts.password) if parts.password else None
    return ProxySpec(
        scheme=scheme,
        host=parts.hostname,
        port=parts.port,
        username=username,
        password=password,
    )
