"""ProxySpec: one proxy endpoint, described once and rendered per engine.

httpx (Vector) wants a URL string; Playwright (Continuum) wants a ``{server, username, password}``
dict. Credentials are kept out of logs via :meth:`ProxySpec.redacted`.
"""

from __future__ import annotations

from dataclasses import dataclass

_PENDING = "Jalon 1.5-G (network): proxy parsing/rendering not implemented yet."


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
        raise NotImplementedError(_PENDING)

    def for_playwright(self) -> dict[str, str]:
        """``{server, username, password}`` for Playwright's ``proxy=`` option."""
        raise NotImplementedError(_PENDING)

    def redacted(self) -> str:
        """A log-safe representation with credentials masked."""
        return self.server_url


def parse_proxy(url: str) -> ProxySpec:
    """Parse a proxy URL (``scheme://user:pass@host:port``) into a :class:`ProxySpec`."""
    raise NotImplementedError(_PENDING)
