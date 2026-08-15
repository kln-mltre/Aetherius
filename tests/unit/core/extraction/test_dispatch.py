"""Tests for core/extraction/dispatch.py

The defaults asserted here are a contract, not an implementation detail: the embedded engine
reproduces them in ``sdks/engine/src/extraction/index.ts``, and a conformance case compares the two.
"""

from __future__ import annotations

import json

import pytest

from aetherius.core.extraction.dispatch import dispatch_extract

pytestmark = pytest.mark.unit

_USERS = json.dumps([{"id": 1, "name": "Ada"}, {"id": 2, "name": "Alan"}]).encode()

_PAGE = b"""<html><body>
  <div class="quote"><span class="text">Hello</span><small class="author">Ada</small></div>
  <a class="next" href="/page/2/">Next</a>
</body></html>"""


def test_json_is_the_default_dialect_and_root_the_default_path() -> None:
    assert dispatch_extract(_USERS, {"ids": {"path": "$[*].id"}}) == {"ids": [1, 2]}
    assert dispatch_extract(b'{"a": 1}', {"all": {}}) == {"all": [{"a": 1}]}


def test_json_where_and_fields_are_forwarded() -> None:
    extracted = dispatch_extract(
        _USERS,
        {
            "users": {
                "from": "json",
                "path": "$[*]",
                "where": "item.name != 'Alan'",
                "fields": {"id": "$.id"},
            }
        },
    )
    assert extracted == {"users": [{"id": 1}]}


def test_html_specs_carry_their_own_defaults() -> None:
    extracted = dispatch_extract(
        _PAGE,
        {
            "quote": {"from": "html", "selector": "span.text::text"},
            "href": {"from": "html", "selector": "a.next", "attr": "href"},
            "first": {"from": "html", "selector": "small.author::text", "multiple": False},
        },
    )
    assert extracted == {"quote": ["Hello"], "href": ["/page/2/"], "first": "Ada"}


def test_any_from_other_than_json_or_text_routes_to_the_html_dialect() -> None:
    # The dispatch is an if/else, not a lookup table; pinning it keeps the embedded twin honest.
    extracted = dispatch_extract(_PAGE, {"quote": {"from": "dom", "selector": "span.text::text"}})
    assert extracted == {"quote": ["Hello"]}


def test_text_dialect_carries_the_content_type_down() -> None:
    extracted = dispatch_extract(
        "Prénom".encode("iso-8859-1"),
        {"raw": {"from": "text"}},
        content_type="text/csv; charset=iso-8859-1",
    )
    assert extracted == {"raw": "Prénom"}


def test_the_three_dialects_coexist_in_one_block() -> None:
    # The text dialect follows the header, the HTML one keeps decoding as UTF-8 with replacement:
    # adding the third form changed nothing for the other two.
    extracted = dispatch_extract(
        _PAGE,
        {"quote": {"from": "html", "selector": "span.text::text"}, "raw": {"from": "text"}},
        content_type="text/html; charset=utf-8",
    )
    assert extracted["quote"] == ["Hello"]
    assert extracted["raw"] == _PAGE.decode()
