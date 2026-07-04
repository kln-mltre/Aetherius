"""Authentication strategies for Vector (Act I): NoAuth, Bearer, Basic, Cookie, CAS form-login."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx
from parsel import Selector


@runtime_checkable
class AuthStrategy(Protocol):
    def prepare(self, client: httpx.Client) -> None:
        """Called once before the first request (e.g., perform a login flow)."""
        ...

    def apply(self, request: httpx.Request) -> httpx.Request:
        """Mutate or replace a request to inject auth headers/cookies. Called per-request."""
        ...


class NoAuth:
    def prepare(self, client: httpx.Client) -> None:
        pass

    def apply(self, request: httpx.Request) -> httpx.Request:
        return request


class BearerAuth:
    def __init__(self, token: str) -> None:
        self._token = token

    def prepare(self, client: httpx.Client) -> None:
        pass

    def apply(self, request: httpx.Request) -> httpx.Request:
        # httpx requests are immutable; re-build with updated headers.
        return httpx.Request(
            method=request.method,
            url=request.url,
            headers={**dict(request.headers), "Authorization": f"Bearer {self._token}"},
            content=request.content,
        )


class BasicAuth:
    def __init__(self, username: str, password: str) -> None:
        self._auth = httpx.BasicAuth(username, password)

    def prepare(self, client: httpx.Client) -> None:
        client.auth = self._auth

    def apply(self, request: httpx.Request) -> httpx.Request:
        return request


class CookieAuth:
    def __init__(self, cookies: dict[str, str]) -> None:
        self._cookies = cookies

    def prepare(self, client: httpx.Client) -> None:
        client.cookies.update(self._cookies)

    def apply(self, request: httpx.Request) -> httpx.Request:
        return request


class CasFormLogin:
    """CAS-style form-login: GET login page → extract hidden fields → POST credentials → capture cookies."""

    def __init__(
        self,
        login_url: str,
        username: str,
        password: str,
        username_field: str = "username",
        password_field: str = "password",
    ) -> None:
        self._login_url = login_url
        self._username = username
        self._password = password
        self._username_field = username_field
        self._password_field = password_field

    def prepare(self, client: httpx.Client) -> None:
        resp = client.get(self._login_url)
        resp.raise_for_status()
        form_data = _extract_form_fields(resp.content)
        form_data[self._username_field] = self._username
        form_data[self._password_field] = self._password
        login_resp = client.post(self._login_url, data=form_data, follow_redirects=True)
        login_resp.raise_for_status()

    def apply(self, request: httpx.Request) -> httpx.Request:
        return request


def _extract_form_fields(html: bytes) -> dict[str, str]:
    """Extract all hidden input fields from the first <form> in *html*."""
    sel = Selector(text=html.decode("utf-8", errors="replace"))
    fields: dict[str, str] = {}
    for inp in sel.css("form input[type=hidden]"):
        name = inp.attrib.get("name", "")
        value = inp.attrib.get("value", "")
        if name:
            fields[name] = value
    return fields
