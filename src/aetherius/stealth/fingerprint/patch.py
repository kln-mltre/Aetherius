"""Injected JavaScript that masks the tell-tale signatures of an automated browser.

Headless/automated Chromium leaks a handful of well-known flags that detection scripts read first:
``navigator.webdriver`` is ``true``, ``window.chrome`` is missing, the permissions API disagrees
with ``Notification.permission``, and the plugin list is empty. This patch, injected before any page
script runs (``context.add_init_script``), brings those back in line with a normal browser. Kept as a
constant string, mirroring the debug overlay pattern, so it is trivially assertable in tests.

Generalized from the ``apply_stealth`` routine of the legacy TikTok project (see legacy_examples/).
"""

from __future__ import annotations

# Masks applied to every frame before its own scripts execute. Deliberately conservative: only the
# high-signal, low-risk flags. Deeper coherence (WebGL, hardware) lives in the fingerprint profile.
FINGERPRINT_PATCH_JS = """
(() => {
  // navigator.webdriver is the single most-checked automation flag.
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

  // Automated Chromium ships without the window.chrome object a real Chrome exposes.
  if (!window.chrome) {
    window.chrome = { runtime: {} };
  }

  // The permissions API must agree with Notification.permission, or the mismatch is a giveaway.
  const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
  if (originalQuery) {
    window.navigator.permissions.query = (parameters) =>
      parameters && parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);
  }

  // A non-empty plugin list looks like a real, GUI browser.
  Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
})();
"""
