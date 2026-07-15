"""Coherent fingerprint profiles: user agent, viewport, locale, timezone and WebGL kept consistent.

A believable fingerprint is not one spoofed field but a *coherent set*: the user agent, the reported
platform and hardware, the locale and the timezone must tell the same story. A profile bundles that
story into (a) Playwright context options applied at context creation, (b) a small init script that
aligns the JavaScript-visible hardware (``navigator.platform``/``hardwareConcurrency``, WebGL
vendor/renderer) with it, and (c) the derived values (client hints, screen) the hardening layer
(``hardening.py``, ``headers.py``) closes the remaining gaps with — all from the same story.

Known limitation: profiles are static presets, not sampled from a real hardware distribution. (The UA
client hints — ``Sec-CH-UA`` / ``navigator.userAgentData`` — are now *derived* from the profile's own
UA version, so they no longer drift from it.) The ML fingerprint model on the roadmap is the intended
upgrade, behind this same interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from ...core.errors import BlueprintValidationError

if TYPE_CHECKING:
    from ...network.geo import GeoHint


@dataclass(frozen=True, slots=True)
class FingerprintProfile:
    """A coherent identity: context options plus the JS patch that keeps hardware in agreement."""

    name: str
    user_agent: str
    viewport: tuple[int, int]
    locale: str
    timezone_id: str
    platform: str
    hardware_concurrency: int
    device_memory: int
    webgl_vendor: str
    webgl_renderer: str
    languages: tuple[str, ...] = field(default=("en-US", "en"))
    # Hardening signals (Jalon H), all coherent with the UA above. ``screen`` is the physical screen
    # (>= viewport, the inner window); ``ua_platform`` is the client-hint platform ("Windows"), which
    # differs from ``navigator.platform`` ("Win32"); ``ua_full_version`` sources the Sec-CH-UA version.
    screen: tuple[int, int] = (1920, 1080)
    device_pixel_ratio: float = 1.0
    ua_platform: str = "Windows"
    ua_full_version: str = "126.0.6478.127"

    @property
    def chrome_major(self) -> str:
        """Major Chromium version driving the client hints (derived from the full version)."""
        return self.ua_full_version.split(".", 1)[0]

    def ua_brands(self) -> tuple[tuple[str, str], ...]:
        """The ``(brand, version)`` list for ``Sec-CH-UA`` / ``userAgentData.brands``.

        Order is fixed per profile so the resulting fingerprint is stable (real Chrome randomises the
        GREASE brand order, but a static, coherent order is indistinguishable to a cross-check).
        """
        major = self.chrome_major
        return (("Not/A)Brand", "8"), ("Chromium", major), ("Google Chrome", major))

    def sec_ch_ua(self) -> str:
        """The ``Sec-CH-UA`` header value, derived from :meth:`ua_brands`."""
        return ", ".join(f'"{brand}";v="{version}"' for brand, version in self.ua_brands())

    def geo_aligned(self, geo: GeoHint) -> FingerprintProfile:
        """Return a copy with timezone/locale/languages aligned to an exit-IP geography.

        A US exit IP behind a ``Europe/Paris`` profile is a tell; when the proxy carries a country the
        profile follows it. Shared by both engines so the alignment logic lives in one place.
        """
        return replace(
            self, timezone_id=geo.timezone_id, locale=geo.locale, languages=geo.languages
        )

    def context_options(self) -> dict[str, object]:
        """Playwright ``new_context``/``launch_persistent_context`` options for this identity."""
        width, height = self.viewport
        return {
            "user_agent": self.user_agent,
            "viewport": {"width": width, "height": height},
            "locale": self.locale,
            "timezone_id": self.timezone_id,
        }

    def init_script(self) -> str:
        """JS injected before page scripts so the hardware fingerprint matches the declared identity."""
        languages = ", ".join(f"'{lang}'" for lang in self.languages)
        return f"""
(() => {{
  Object.defineProperty(navigator, 'platform', {{ get: () => '{self.platform}' }});
  Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {self.hardware_concurrency} }});
  Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {self.device_memory} }});
  Object.defineProperty(navigator, 'languages', {{ get: () => [{languages}] }});

  // Align the WebGL vendor/renderer strings, a common cross-check against the UA.
  const getParameter = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function (parameter) {{
    if (parameter === 37445) return '{self.webgl_vendor}';    // UNMASKED_VENDOR_WEBGL
    if (parameter === 37446) return '{self.webgl_renderer}';  // UNMASKED_RENDERER_WEBGL
    return getParameter.call(this, parameter);
  }};
}})();
"""


# Registry of named profiles. Small on purpose; add entries as real coverage needs them.
_PROFILES: dict[str, FingerprintProfile] = {
    "chrome-desktop": FingerprintProfile(
        name="chrome-desktop",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        viewport=(1280, 800),
        locale="en-US",
        timezone_id="America/New_York",
        platform="Win32",
        hardware_concurrency=8,
        device_memory=8,
        webgl_vendor="Google Inc. (Intel)",
        webgl_renderer=("ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ),
}


def get_profile(name: str) -> FingerprintProfile:
    """Return the named profile, or raise a typed error listing the known ones."""
    profile = _PROFILES.get(name)
    if profile is None:
        raise BlueprintValidationError(
            f"Unknown fingerprint profile {name!r} (known: {sorted(_PROFILES)})."
        )
    return profile
