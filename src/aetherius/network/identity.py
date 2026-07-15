"""NetworkIdentity: the resolved egress + geo for a run, and how it is resolved.

Resolution order: the Blueprint's ``options.proxy`` wins; otherwise the environment default/pool from
settings; otherwise no proxy. The result travels to both engines (Vector httpx, Continuum Playwright)
and drives geo-coherent fingerprint overrides and the WebRTC leak guard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.errors import BlueprintValidationError
from .geo import GeoHint, geo_hint
from .pool import ProxyPool, RotationStrategy
from .proxy import ProxySpec, parse_proxy

_KNOWN_KEYS = frozenset({"url", "pool", "rotate", "geo", "impersonate"})


@dataclass(frozen=True, slots=True)
class NetworkIdentity:
    """The effective network identity for one run."""

    proxy: ProxySpec | None = None
    geo: GeoHint | None = None
    # TLS impersonation target for Vector (e.g. "chrome"); None keeps the stock httpx handshake.
    impersonate: str | None = None


def resolve_identity(option: Any, *, run_key: str | None = None) -> NetworkIdentity:
    """Resolve the effective identity from ``options.proxy`` and settings, for this run.

    ``run_key`` scopes rotation stickiness (e.g. a schedule id) when the strategy calls for it.
    """
    if option is None:
        source = _settings_source()
        if source is None:
            return NetworkIdentity()
    elif isinstance(option, str):
        source = {"url": option}
    elif isinstance(option, dict):
        source = option
    else:
        raise BlueprintValidationError(
            "options.proxy must be a proxy URL string or an object with 'url'/'pool'."
        )
    return _decode(source, run_key=run_key)


def _settings_source() -> dict[str, Any] | None:
    """Build a proxy source from the environment defaults, or ``None`` when none is configured."""
    # Imported lazily: config.settings imports network.pool, so a top-level import here would cycle.
    from ..config.settings import get_settings

    settings = get_settings()
    if settings.proxy_pool:
        return {"pool": list(settings.proxy_pool), "rotate": settings.proxy_rotate}
    if settings.proxy_url:
        return {"url": settings.proxy_url, "rotate": settings.proxy_rotate}
    return None


def _decode(source: dict[str, Any], *, run_key: str | None) -> NetworkIdentity:
    """Decode a validated proxy object into a :class:`NetworkIdentity`."""
    unknown = set(source) - _KNOWN_KEYS
    if unknown:
        raise BlueprintValidationError(
            f"Unknown options.proxy keys {sorted(unknown)} (allowed: {sorted(_KNOWN_KEYS)})."
        )

    proxies = _proxies(source)
    strategy: RotationStrategy = source.get("rotate", "per_run")
    proxy = ProxyPool(tuple(proxies), strategy).select(run_key)

    geo = geo_hint(source["geo"]) if source.get("geo") else None
    impersonate = _impersonate(source.get("impersonate"))
    return NetworkIdentity(proxy=proxy, geo=geo, impersonate=impersonate)


def _proxies(source: dict[str, Any]) -> list[ProxySpec]:
    """Parse the ``pool`` list or the single ``url`` into proxy specs."""
    pool = source.get("pool")
    if pool is not None:
        if not isinstance(pool, (list, tuple)) or not pool:
            raise BlueprintValidationError("options.proxy.pool must be a non-empty list of URLs.")
        return [parse_proxy(str(url)) for url in pool]
    url = source.get("url")
    if url:
        return [parse_proxy(str(url))]
    raise BlueprintValidationError("options.proxy requires a 'url' or a 'pool'.")


def _impersonate(value: Any) -> str | None:
    """Normalise the impersonation target: ``True`` -> ``"chrome"``, a string is kept, else off."""
    if value is None or value is False:
        return None
    if value is True:
        return "chrome"
    if isinstance(value, str):
        return value
    raise BlueprintValidationError(
        "options.proxy.impersonate must be a target name (e.g. 'chrome') or true."
    )
