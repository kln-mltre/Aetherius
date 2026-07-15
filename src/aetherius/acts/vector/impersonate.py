"""Browser-TLS impersonation transport for Vector (JA3/JA4), backed by curl_cffi ([network] extra).

The stock httpx handshake has a recognisable TLS fingerprint; against Cloudflare/Akamai that alone
can get a request blocked. curl_cffi replays a real browser's ClientHello, defeating JA3/JA4
fingerprinting. It lives behind the optional ``[network]`` extra and is imported lazily, so the base
install and ``import aetherius`` stay light. Its responses are requests-shaped
(``status_code``/``headers``/``content``/``text``), matching what VectorClient and the driver read.
"""

from __future__ import annotations

from typing import Any

from ...core.errors import DependencyError, NetworkError, TimeoutError

_EXTRA_HINT = (
    "TLS impersonation requires the [network] extra. Install it with:\n"
    '    pip install "aetherius[network]"'
)


def _import_curl_requests() -> Any:
    """Import curl_cffi's requests API, or raise a typed, actionable error."""
    try:
        from curl_cffi import requests as curl_requests
    except ImportError as exc:  # extra [network] not installed
        raise DependencyError(_EXTRA_HINT, extra="network") from exc
    return curl_requests


class ImpersonateClient:
    """A minimal client whose TLS handshake impersonates a real browser.

    Shaped like the send half of :class:`~aetherius.acts.vector.client.VectorClient`: one ``send``
    per request, transport failures mapped to Aetherius' typed errors so retries and reporting stay
    uniform across both transports.
    """

    def __init__(
        self,
        *,
        impersonate: str,
        proxy: str | None = None,
        timeout_ms: int = 30_000,
    ) -> None:
        curl_requests = _import_curl_requests()
        self._impersonate = impersonate
        self._timeout = timeout_ms / 1000
        proxies = {"http": proxy, "https": proxy} if proxy else None
        self._session = curl_requests.Session(impersonate=impersonate, proxies=proxies)

    def send(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        data: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        """Issue one impersonated request. Raises TimeoutError/NetworkError on transport failure."""
        from curl_cffi.requests.exceptions import RequestException, Timeout

        try:
            return self._session.request(
                method=method.upper(),
                url=url,
                headers=headers,
                json=json,
                data=data,
                params=params,
                timeout=self._timeout,
            )
        except Timeout as exc:
            raise TimeoutError(f"Request timed out: {method} {url}") from exc
        except RequestException as exc:
            raise NetworkError(f"Impersonation transport error: {exc}") from exc

    def close(self) -> None:
        self._session.close()
