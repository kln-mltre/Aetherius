"""Coherent fingerprint profiles: user agent, viewport, locale, timezone and WebGL kept consistent.

A believable fingerprint is not one spoofed field but a *coherent set*: the user agent, the reported
platform and hardware, the locale and the timezone must tell the same story. A profile bundles that
story into (a) Playwright context options applied at context creation, and (b) a small init script
that aligns the JavaScript-visible hardware (``navigator.platform``/``hardwareConcurrency``,
WebGL vendor/renderer) with it.

Known limitation: profiles are static presets, not sampled from a real hardware distribution, and the
overridden UA version may drift from the underlying Chromium build's client hints. The ML fingerprint
model on the roadmap is the intended upgrade, behind this same interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...core.errors import BlueprintValidationError


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
