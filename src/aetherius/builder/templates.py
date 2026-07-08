"""Starter Blueprint templates per Act and per common use case.

Each template is a small, zero-config demonstration against a public endpoint, returned as a fresh
:class:`~.factory.BlueprintDraft` the Studio can then edit. Every template is guaranteed valid by a
test that runs it through the canonical build path, so "Load a template" always yields a runnable
starting point.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..core.errors import BuilderError
from .factory import BlueprintDraft, StepDraft


@dataclass(frozen=True)
class TemplateInfo:
    """A template's identity for the picker: a stable key, its Act, a title and a one-liner."""

    key: str
    act: str
    title: str
    summary: str


def _vector_api_fetch() -> BlueprintDraft:
    return BlueprintDraft(
        name="api.fetch",
        act="vector",
        description="Fetch a JSON collection over HTTP and extract fields.",
        steps=[
            StepDraft(
                action="http.request",
                id="fetch",
                params={
                    "method": "GET",
                    "url": "https://jsonplaceholder.typicode.com/posts",
                    "expect": {"status": 200},
                    "extract": {
                        "posts": {
                            "from": "json",
                            "path": "$[*]",
                            "fields": {"id": "$.id", "title": "$.title"},
                        }
                    },
                },
            )
        ],
        outputs={"posts": "{{ steps.fetch.posts }}"},
    )


def _continuum_scrape() -> BlueprintDraft:
    return BlueprintDraft(
        name="site.scrape",
        act="continuum",
        description="Open a page, wait for content, and extract a list of records.",
        steps=[
            StepDraft(action="navigate", params={"url": "https://quotes.toscrape.com/"}),
            StepDraft(action="wait_for", params={"selector": ".quote"}),
            StepDraft(
                action="extract",
                id="data",
                params={
                    "outputs": {
                        "quotes": {
                            "each": ".quote",
                            "fields": {
                                "text": {"selector": ".text", "as": "text"},
                                "author": {"selector": ".author", "as": "text"},
                            },
                        }
                    }
                },
            ),
        ],
        outputs={"quotes": "{{ steps.data.quotes }}"},
    )


def _continuum_login() -> BlueprintDraft:
    return BlueprintDraft(
        name="site.login",
        act="continuum",
        description="Log in through a form, keeping the password as a runtime secret.",
        inputs={"username": {"type": "string", "required": True}},
        secrets=["password"],
        steps=[
            StepDraft(action="navigate", params={"url": "https://quotes.toscrape.com/login"}),
            StepDraft(
                action="fill", params={"selector": "#username", "value": "{{ inputs.username }}"}
            ),
            StepDraft(
                action="fill", params={"selector": "#password", "value": "{{ secrets.password }}"}
            ),
            StepDraft(action="click", params={"selector": "input[type='submit']"}),
            StepDraft(
                action="wait_for",
                params={"selector": "a[href='/logout']", "on_timeout": "fail:LOGIN_FAILED"},
            ),
        ],
    )


# key -> (TemplateInfo, builder). The builder returns a fresh draft on every call.
_TEMPLATES: dict[str, tuple[TemplateInfo, Callable[[], BlueprintDraft]]] = {
    "vector.api-fetch": (
        TemplateInfo(
            "vector.api-fetch",
            "vector",
            "API fetch",
            "GET a JSON collection and extract fields (jsonplaceholder).",
        ),
        _vector_api_fetch,
    ),
    "continuum.scrape": (
        TemplateInfo(
            "continuum.scrape",
            "continuum",
            "Scrape a page",
            "Navigate, wait, extract records (quotes.toscrape.com).",
        ),
        _continuum_scrape,
    ),
    "continuum.login": (
        TemplateInfo(
            "continuum.login",
            "continuum",
            "Form login",
            "Fill a login form with an input and a secret (quotes.toscrape.com).",
        ),
        _continuum_login,
    ),
}


def list_templates(act: str | None = None) -> list[TemplateInfo]:
    """Every template, optionally filtered to a single *act*, in registration order."""
    infos = [info for info, _ in _TEMPLATES.values()]
    return [info for info in infos if act is None or info.act == act]


def template_draft(key: str) -> BlueprintDraft:
    """Return a fresh draft for template *key* or raise :class:`BuilderError`."""
    entry = _TEMPLATES.get(key)
    if entry is None:
        raise BuilderError(f"Unknown template {key!r} (known: {sorted(_TEMPLATES)}).")
    return entry[1]()
