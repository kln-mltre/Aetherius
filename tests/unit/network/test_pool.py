"""Tests for network/pool.py — proxy rotation strategies."""

from __future__ import annotations

import pytest

from aetherius.core.errors import BlueprintValidationError
from aetherius.network.pool import ProxyPool
from aetherius.network.proxy import ProxySpec

pytestmark = pytest.mark.unit

_A = ProxySpec("http", "a", 1)
_B = ProxySpec("http", "b", 2)
_C = ProxySpec("http", "c", 3)


def _pool(strategy: str) -> ProxyPool:
    return ProxyPool((_A, _B, _C), strategy)  # type: ignore[arg-type]


def test_single_proxy_returns_it_for_every_strategy() -> None:
    for strategy in ("per_run", "round_robin", "random", "sticky"):
        pool = ProxyPool((_A,), strategy)  # type: ignore[arg-type]
        assert pool.select("k") is _A


def test_round_robin_cycles_deterministically() -> None:
    pool = _pool("round_robin")
    picks = [pool.select() for _ in range(7)]
    assert picks == [_A, _B, _C, _A, _B, _C, _A]


def test_sticky_is_stable_per_key() -> None:
    pool = _pool("sticky")
    first = pool.select("blueprint-x")
    assert pool.select("blueprint-x") is first
    assert pool.select("blueprint-x") is first


def test_sticky_spreads_across_keys() -> None:
    pool = _pool("sticky")
    # Over enough distinct keys, more than one proxy is used (the map is not degenerate).
    chosen = {pool.select(f"bp-{i}") for i in range(50)}
    assert len(chosen) > 1


@pytest.mark.parametrize("strategy", ["per_run", "random"])
def test_random_like_strategies_stay_within_the_pool(strategy: str) -> None:
    pool = _pool(strategy)
    for _ in range(20):
        assert pool.select() in (_A, _B, _C)


def test_empty_pool_is_rejected() -> None:
    with pytest.raises(BlueprintValidationError, match="at least one"):
        ProxyPool(())


def test_unknown_strategy_is_rejected() -> None:
    with pytest.raises(BlueprintValidationError, match="strategy"):
        ProxyPool((_A,), "spin")  # type: ignore[arg-type]
