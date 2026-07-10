"""Unit tests for recorder/selector_synth.py: the (browser-free) selector ranking policy."""

from __future__ import annotations

import pytest

from aetherius.recorder.selector_synth import Candidate, ElementDescriptor, synthesize

pytestmark = pytest.mark.unit


def _descriptor(*candidates: Candidate, css_path: str = "body > div > button") -> ElementDescriptor:
    return ElementDescriptor(tag="button", css_path=css_path, candidates=candidates)


def test_testid_wins_over_id_and_the_rest() -> None:
    choice = synthesize(
        _descriptor(
            Candidate("id", "#submit", "css", True),
            Candidate("testid", '[data-testid="go"]', "css", True),
            Candidate("name", 'button[name="go"]', "css", True),
        )
    )
    assert choice.selector == '[data-testid="go"]'
    assert choice.selector_type == "css"
    assert choice.strategy == "testid"


def test_priority_order_falls_through_to_the_next_present_strategy() -> None:
    # No testid/id: name is the best available.
    choice = synthesize(
        _descriptor(
            Candidate("name", 'input[name="q"]', "css", True),
            Candidate("aria", '[aria-label="Search"]', "css", True),
        )
    )
    assert choice.selector == 'input[name="q"]'
    assert choice.strategy == "name"


def test_non_unique_candidate_is_skipped_for_the_next_unique_one() -> None:
    choice = synthesize(
        _descriptor(
            Candidate("id", "#dup", "css", False),  # present but not unique on the page
            Candidate("name", 'input[name="email"]', "css", True),
        )
    )
    assert choice.selector == 'input[name="email"]'
    assert choice.strategy == "name"


def test_href_is_preferred_over_ambiguous_text_for_links() -> None:
    # A link whose text ("License") is not unique on the page must fall back to its href, not text.
    choice = synthesize(
        ElementDescriptor(
            tag="a",
            css_path="div > a",
            candidates=(
                Candidate("href", 'a[href="/repo/LICENSE"]', "css", True),
                Candidate("text", "License", "text", False),  # 5 elements contain "License"
            ),
        )
    )
    assert choice.selector == 'a[href="/repo/LICENSE"]'
    assert choice.strategy == "href"


def test_text_strategy_carries_its_selector_type() -> None:
    choice = synthesize(_descriptor(Candidate("text", "Sign in", "text", True)))
    assert choice.selector == "Sign in"
    assert choice.selector_type == "text"
    assert choice.strategy == "text"


def test_falls_back_to_css_path_when_nothing_is_unique() -> None:
    choice = synthesize(
        _descriptor(
            Candidate("id", "#dup", "css", False),
            Candidate("name", 'input[name="dup"]', "css", False),
            css_path="form > div:nth-of-type(2) > input",
        )
    )
    assert choice.selector == "form > div:nth-of-type(2) > input"
    assert choice.selector_type == "css"
    assert choice.strategy == "css_path"


def test_falls_back_to_tag_when_even_css_path_is_missing() -> None:
    choice = synthesize(ElementDescriptor(tag="button", css_path="", candidates=()))
    assert choice.selector == "button"
