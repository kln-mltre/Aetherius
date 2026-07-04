"""HTTP client wrapper: httpx.Client with tenacity-based retries and pluggable auth."""

from __future__ import annotations

from typing import Any

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


def _build_retry(retries: RetriesOptions) -> Any:
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
        retry=retry_if_exception_type(_RETRYABLE),
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
    ) -> None:
        self._timeout = timeout_ms / 1000
        self._retries = retries or RetriesOptions()
        self._auth: AuthStrategy = auth or NoAuth()
        self._client = httpx.Client(timeout=self._timeout, follow_redirects=True)
        self._auth.prepare(self._client)
        self._retry_decorator = _build_retry(self._retries)

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
    ) -> httpx.Response:
        """Send an HTTP request with optional auth, retries, and status assertion.

        Raises:
            ActionError: if both json and form are provided.
            TimeoutError: on httpx timeout.
            RetryExhaustedError: after all retry attempts fail.
            NetworkError: on other transport failures.
            StatusAssertionError: if expected_status is set and response status doesn't match.
        """
        from ...core.errors import ActionError

        if json is not None and form is not None:
            raise ActionError("Cannot set both 'json' and 'form' on the same http.request step.")

        req = httpx.Request(
            method=method.upper(),
            url=url,
            headers=headers or {},
            params=params,
            json=json,
            data=form,
        )
        req = self._auth.apply(req)

        def _send() -> httpx.Response:
            return self._client.send(req)

        try:
            if self._retry_decorator is not None:
                response: httpx.Response = self._retry_decorator(_send)()
            else:
                response = _send()
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"Request timed out: {method} {url}") from exc
        except RetryError as exc:
            raise RetryExhaustedError(
                f"All {self._retries.max} retry attempts failed: {method} {url}",
                last_error=exc,
            ) from exc
        except httpx.TransportError as exc:
            raise NetworkError(f"Transport error: {exc}") from exc

        if expected_status is not None and response.status_code != expected_status:
            raise StatusAssertionError(
                expected=expected_status,
                actual=response.status_code,
                url=url,
                body_preview=response.text,
            )

        return response

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "VectorClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
