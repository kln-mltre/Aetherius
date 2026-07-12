"""Tests for store/state.py — key/value state and the compare_and_set transition signal."""

from __future__ import annotations

import pytest

from aetherius.store import Store

pytestmark = pytest.mark.unit


def test_get_missing_returns_none(store: Store) -> None:
    assert store.state.get("scope", "key") is None


def test_set_then_get(store: Store) -> None:
    store.state.set("sch-1", "stock", "in-stock")
    assert store.state.get("sch-1", "stock") == "in-stock"


def test_set_overwrites(store: Store) -> None:
    store.state.set("sch-1", "stock", "in-stock")
    store.state.set("sch-1", "stock", "out-of-stock")
    assert store.state.get("sch-1", "stock") == "out-of-stock"


def test_scope_isolates_keys(store: Store) -> None:
    store.state.set("sch-1", "stock", "a")
    store.state.set("sch-2", "stock", "b")
    assert store.state.get("sch-1", "stock") == "a"
    assert store.state.get("sch-2", "stock") == "b"


def test_compare_and_set_signals_first_write_and_transitions(store: Store) -> None:
    # First write: no previous value, so it counts as a change.
    assert store.state.compare_and_set("sch-1", "stock", "out-of-stock") is True
    # Identical value: not a change (this is what suppresses repeat alerts).
    assert store.state.compare_and_set("sch-1", "stock", "out-of-stock") is False
    # Transition to a new value: a change again.
    assert store.state.compare_and_set("sch-1", "stock", "in-stock") is True
    # And it did persist the latest value.
    assert store.state.get("sch-1", "stock") == "in-stock"
