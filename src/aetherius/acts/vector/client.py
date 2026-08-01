"""HTTP client wrapper: httpx.Client with tenacity-based retries and pluggable auth.

Two transports share one request pipeline (guard, retries, status assertion): the default httpx
client (native HTTP/HTTPS, plus SOCKS5 with the [network] extra), and an optional browser-TLS
impersonation transport (curl_cffi, also [network]) selected when a run asks to defeat JA3/JA4
fingerprinting. See acts/vector/impersonate.py and docs/network.md.
"""

from __future__ import annotations

from typing import Any, Protocol, cast

import httpx
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
)

from ...core.blueprint.models import RetriesOptions
from ...core.errors import NetworkError, RetryExhaustedError, StatusAssertionError, TimeoutError
from .auth import AuthStrategy, NoAuth

_RETRYABLE = (httpx.TransportError, httpx.TimeoutException)


class HttpResponse(Protocol):
    """The response surface both transports expose and the driver reads (read-only)."""

    @property
    def status_code(self) -> int: ...
    @property
    def headers(self) -> Any: ...
    @property
    def content(self) -> bytes: ...
    @property
    def text(self) -> str: ...


def _build_retry(retries: RetriesOptions, exc_types: tuple[type[BaseException], ...]) -> Any:
    """Return a tenacity retry decorator configured from Blueprint options."""
    if retries.max == 0:
        return None
    stop = stop_after_attempt(retries.max + 1)
    wait: Any
    if retries.backoff == "exponential":
        wait = wait_exponential(multiplier=1, min=1, max=30)
    elif retries.backoff == "linear":
        wait = wait_fixed(1)
    else:
        wait = wait_fixed(0)
    return retry(
        retry=retry_if_exception_type(exc_types),
        stop=stop,
        wait=wait,
        reraise=True,
    )


class VectorClient:
    def __init__(
        self,
        *,
        timeout_ms: int = 30_000,
        retries: RetriesOptions | None = None,
        auth: AuthStrategy | None = None,
        proxy: str | None = None,
        impersonate: str | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self._timeout = timeout_ms / 1000
        self._retries = retries or RetriesOptions()
        self._auth: AuthStrategy = auth or NoAuth()
        self._impersonate_client: Any = None
        # Fingerprint header identity (Jalon H): merged under the request's explicit headers on the
        # httpx path. The impersonation path skips them — curl_cffi already carries a coherent set.
        self._default_headers = default_headers or {}

        if impersonate is not None:
            # Impersonation replaces the httpx transport entirely (curl_cffi carries its own TLS and
            # SOCKS support). Retries key off Aetherius' typed errors raised by the impersonation send.
            from .impersonate import ImpersonateClient

            self._impersonate_client = ImpersonateClient(
                impersonate=impersonate, proxy=proxy, timeout_ms=timeout_ms
            )
            self._client: httpx.Client | None = None
            self._retry_decorator = _build_retry(self._retries, (NetworkError,))
        else:
            client_kwargs: dict[str, Any] = {"timeout": self._timeout, "follow_redirects": True}
            if proxy is not None:
                client_kwargs["proxy"] = proxy
            self._client = httpx.Client(**client_kwargs)
            self._auth.prepare(self._client)
            self._retry_decorator = _build_retry(self._retries, _RETRYABLE)

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        form: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        expected_status: int | None = None,
    ) -> HttpResponse:
        """Send an HTTP request with optional auth, retries, and status assertion.

        Raises:
            ActionError: if both json and form are provided.
            TimeoutError: on transport timeout.
            RetryExhaustedError: after all retry attempts fail.
            NetworkError: on other transport failures.
            StatusAssertionError: if expected_status is set and response status doesn't match.
        """
        from ...core.errors import ActionError

        if json is not None and form is not None:
            raise ActionError("Cannot set both 'json' and 'form' on the same http.request step.")

        if self._impersonate_client is not None:
            response: HttpResponse = self._request_impersonated(
                method, url, headers, json, form, params
            )
        else:
            response = self._request_httpx(method, url, headers, json, form, params)

        if expected_status is not None and response.status_code != expected_status:
            raise StatusAssertionError(
                expected=expected_status,
                actual=response.status_code,
                url=url,
                body_preview=response.text,
            )

        return response

    def _request_httpx(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        json: Any | None,
        form: dict[str, str] | None,
        params: dict[str, str] | None,
    ) -> httpx.Response:
        # Defaults first, then the Blueprint's explicit headers on top: httpx.Headers is
        # case-insensitive, so an explicit "user-agent" overrides the default "User-Agent" cleanly.
        merged = httpx.Headers(self._default_headers)
        merged.update(headers or {})
        req = httpx.Request(
            method=method.upper(),
            url=url,
            headers=merged,
            params=params,
            json=json,
            data=form,
        )
        assert self._client is not None  # invariant: the httpx path is chosen only with a client
        # httpx attaches the client's cookies in `build_request`, not in `send`. This path builds
        # its own Request (to keep header precedence explicit), so without this line a session
        # captured by one step — a form login, a Set-Cookie — would never reach the next one.
        # The jar respects an explicit `Cookie` header: the Blueprint's own always wins.
        self._client.cookies.set_cookie_header(req)
        req = self._auth.apply(req)

        def _send() -> httpx.Response:
            assert self._client is not None
            return self._client.send(req)

        try:
            if self._retry_decorator is not None:
                return self._retry_decorator(_send)()  # type: ignore[no-any-return]
            return _send()
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"Request timed out: {method} {url}") from exc
        except RetryError as exc:
            raise RetryExhaustedError(
                f"All {self._retries.max} retry attempts failed: {method} {url}",
                last_error=exc,
            ) from exc
        except httpx.TransportError as exc:
            raise NetworkError(f"Transport error: {exc}") from exc

    def _request_impersonated(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        json: Any | None,
        form: dict[str, str] | None,
        params: dict[str, str] | None,
    ) -> HttpResponse:
        def _send() -> HttpResponse:
            return cast(
                HttpResponse,
                self._impersonate_client.send(
                    method, url, headers=headers, json=json, data=form, params=params
                ),
            )

        # The impersonation send raises typed errors; tenacity (reraise=True) re-raises them as-is.
        if self._retry_decorator is not None:
            return self._retry_decorator(_send)()  # type: ignore[no-any-return]
        return _send()

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
        if self._impersonate_client is not None:
            self._impersonate_client.close()

    def __enter__(self) -> "VectorClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
