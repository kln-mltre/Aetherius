"""Robust selector synthesis: prefer data-testid, aria and text before fragile css paths.

The in-page capture script (``_capture_js.py``) does the DOM work: for a target element it forms
candidate selector strings (escaping with the browser's ``CSS.escape``) and, crucially, tests each
for *uniqueness* on the live page (``querySelectorAll(sel).length === 1``). This module owns the
policy that is worth testing on its own: given those candidates, which one to keep, in what order,
and when to fall back to a positional css path. Keeping the ranking here — pure, browser-free — means
it runs in the base test suite while the DOM facts it consumes are produced by the browser.

A selector survives a page far better when it is anchored on intent (a test id, a name, a label,
visible text) than on a brittle ``div > div:nth-child(3) > span`` chain, so intent-based strategies
are ranked first and the positional path is only ever the last resort.
"""

from __future__ import annotations

from dataclasses import dataclass

# Strategy names, in the order we trust them. First unique candidate wins; css_path is the fallback.
# data-testid/-test/-cy/-qa are added by developers precisely as stable hooks, so they rank highest;
# a positional css path is the most fragile and ranks below everything intent-based.
_PRIORITY: tuple[str, ...] = ("testid", "id", "name", "aria", "role", "text")


@dataclass(frozen=True, slots=True)
class Candidate:
    """One selector the page offers for an element, tagged with its strategy and uniqueness.

    ``unique`` is measured in-page against the live DOM; a non-unique candidate is skipped because a
    Blueprint action would hit Playwright's strict mode on an ambiguous target.
    """

    strategy: str
    selector: str
    selector_type: str  # "css" | "text" | "xpath"
    unique: bool


@dataclass(frozen=True, slots=True)
class ElementDescriptor:
    """Everything the capture script observed about a target element.

    ``candidates`` feed selector synthesis; ``name``/``field_type``/``autocomplete`` feed the
    credential heuristic in the blueprint recorder. One descriptor, two consumers, no duplication.
    """

    tag: str
    css_path: str
    candidates: tuple[Candidate, ...] = ()
    text: str | None = None
    name: str | None = None
    field_type: str | None = None
    autocomplete: str | None = None


@dataclass(frozen=True, slots=True)
class SelectorChoice:
    """The chosen selector and how to interpret it (``css`` is the Blueprint default)."""

    selector: str
    selector_type: str = "css"
    strategy: str = "css_path"


def synthesize(descriptor: ElementDescriptor) -> SelectorChoice:
    """Pick the most robust selector for *descriptor*.

    Walks the trusted strategies in order and returns the first candidate that is unique on the
    page; if none qualifies, falls back to the positional css path (or the bare tag if even that is
    missing, so a caller always gets something usable rather than an empty selector).
    """
    by_strategy: dict[str, Candidate] = {}
    for candidate in descriptor.candidates:
        # Keep the first candidate seen per strategy: the capture script emits them best-first.
        by_strategy.setdefault(candidate.strategy, candidate)

    for strategy in _PRIORITY:
        chosen = by_strategy.get(strategy)
        if chosen is not None and chosen.unique:
            return SelectorChoice(chosen.selector, chosen.selector_type, strategy)

    fallback = descriptor.css_path or descriptor.tag
    return SelectorChoice(fallback, "css", "css_path")
