"""Fingerprint hardening (Phase 1.5, Jalon H): the signals the base profile leaves untouched.

The coherent profile (``profile.py``) covers UA / viewport / locale / timezone / platform / cores /
memory / WebGL1. This closes the remaining high-signal gaps that advanced anti-bot systems
cross-check: Canvas and AudioContext fingerprints, font enumeration (via ``measureText``), client
hints (``Sec-CH-UA`` / ``navigator.userAgentData``) aligned with the UA, screen dimensions /
``devicePixelRatio``, and WebGL2. Every override is derived from the active
:class:`~aetherius.stealth.fingerprint.profile.FingerprintProfile` — one consistent story, not
scattered spoofs.

Canvas/Audio/measureText noise is *deterministic per profile*, never random per call: a fingerprint
that changes on every read is itself a tell. A profile-derived seed feeds a small integer hash so two
reads of the same canvas within a run return the same bytes, while two profiles differ. See
docs/phase-1.5/h-fingerprint.md.
"""

from __future__ import annotations

import hashlib
import json

from .profile import FingerprintProfile


def _seed(profile: FingerprintProfile) -> int:
    """A stable 32-bit seed for this profile's Canvas/Audio noise (same profile -> same seed)."""
    raw = f"{profile.name}|{profile.user_agent}|{profile.screen}".encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:4], "big")


def hardening_init_script(profile: FingerprintProfile) -> str:
    """Return the init script closing the Canvas/Audio/fonts/UA-CH/screen/WebGL2 gaps.

    Kept coherent with *profile* so the added signals tell the same story as the base identity.
    Injected after :meth:`FingerprintProfile.init_script` so it builds on the same UA/WebGL identity.
    """
    screen_w, screen_h = profile.screen
    brands = [{"brand": brand, "version": version} for brand, version in profile.ua_brands()]
    # Full-version list: GREASE brand carries a full-looking version, the real brands the profile's.
    full_versions = [
        {
            "brand": brand,
            "version": "8.0.0.0" if brand == "Not/A)Brand" else profile.ua_full_version,
        }
        for brand, version in profile.ua_brands()
    ]
    consts = f"""
  const SEED = {_seed(profile)};
  const SCREEN = {{ width: {screen_w}, height: {screen_h}, availWidth: {screen_w},
                   availHeight: {screen_h - 40}, colorDepth: 24, pixelDepth: 24 }};
  const DPR = {profile.device_pixel_ratio};
  const UA_PLATFORM = {json.dumps(profile.ua_platform)};
  const UA_FULL_VERSION = {json.dumps(profile.ua_full_version)};
  const BRANDS = {json.dumps(brands)};
  const FULL_VERSIONS = {json.dumps(full_versions)};
  const WEBGL_VENDOR = {json.dumps(profile.webgl_vendor)};
  const WEBGL_RENDERER = {json.dumps(profile.webgl_renderer)};
"""
    return "(() => {\n" + consts + _HARDENING_BODY + "\n})();\n"


# The static half of the init script. Uses the constants declared above; no Python interpolation here,
# so its braces stay literal. A window marker makes the guard assertable from a browser test.
_HARDENING_BODY = r"""
  window.__aetherius_hardening = true;

  // Deterministic per-index perturbation in {-1, 0, 1}: a pure function of (SEED, i), so the same
  // pixel/sample always shifts the same way — stable across reads, different across profiles.
  const jitter = (i) => {
    let h = (SEED + i) | 0;
    h = Math.imul(h ^ (h >>> 15), 2246822519);
    h = Math.imul(h ^ (h >>> 13), 3266489917);
    h = (h ^ (h >>> 16)) >>> 0;
    return (h % 3) - 1;
  };
  const strSeed = (s) => { let h = SEED; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return h; };
  const clamp = (v) => (v < 0 ? 0 : v > 255 ? 255 : v);

  // ── Canvas ────────────────────────────────────────────────────────────────
  // Read from an offscreen copy of the original pixels every time, so the noise never accumulates
  // (a second toDataURL/getImageData sees the same source, not an already-noised canvas).
  const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
  const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
  const origToBlob = HTMLCanvasElement.prototype.toBlob;

  const noisedCopy = (canvas) => {
    const w = canvas.width, h = canvas.height;
    const off = document.createElement('canvas');
    off.width = w; off.height = h;
    const octx = off.getContext('2d');
    if (w && h) {
      octx.drawImage(canvas, 0, 0);
      const img = origGetImageData.call(octx, 0, 0, w, h);
      const d = img.data;
      for (let i = 0; i < d.length; i += 4) {
        d[i] = clamp(d[i] + jitter(i));
        d[i + 1] = clamp(d[i + 1] + jitter(i + 1));
        d[i + 2] = clamp(d[i + 2] + jitter(i + 2));
      }
      octx.putImageData(img, 0, 0);
    }
    return off;
  };

  HTMLCanvasElement.prototype.toDataURL = function (...args) {
    return origToDataURL.apply(noisedCopy(this), args);
  };
  HTMLCanvasElement.prototype.toBlob = function (callback, ...rest) {
    return origToBlob.call(noisedCopy(this), callback, ...rest);
  };
  CanvasRenderingContext2D.prototype.getImageData = function (sx, sy, sw, sh, ...rest) {
    const img = origGetImageData.call(this, sx, sy, sw, sh, ...rest);
    const d = img.data;
    for (let i = 0; i < d.length; i += 4) {
      d[i] = clamp(d[i] + jitter(i));
      d[i + 1] = clamp(d[i + 1] + jitter(i + 1));
      d[i + 2] = clamp(d[i + 2] + jitter(i + 2));
    }
    return img;
  };

  // ── Fonts (measureText) ─────────────────────────────────────────────────────
  // Font enumeration is driven by text metrics with fallback fonts; a sub-pixel, deterministic shift
  // on the width breaks the enumeration signal while staying stable per (text, font).
  const origMeasureText = CanvasRenderingContext2D.prototype.measureText;
  CanvasRenderingContext2D.prototype.measureText = function (text) {
    const metrics = origMeasureText.apply(this, arguments);
    const delta = (jitter(strSeed(String(text) + this.font)) * 3 + 1) * 1e-3;
    return new Proxy(metrics, {
      get(target, prop) {
        if (prop === 'width') return target.width + delta;
        const value = target[prop];
        return typeof value === 'function' ? value.bind(target) : value;
      },
    });
  };

  // ── AudioContext ─────────────────────────────────────────────────────────────
  // Perturb each channel buffer once (guarded by a WeakSet), so reads are stable and non-accumulating.
  const origGetChannelData = AudioBuffer.prototype.getChannelData;
  const audioSeen = new WeakSet();
  AudioBuffer.prototype.getChannelData = function (channel) {
    const data = origGetChannelData.call(this, channel);
    if (!audioSeen.has(data)) {
      audioSeen.add(data);
      for (let i = 0; i < data.length; i += 100) data[i] = data[i] + jitter(i) * 1e-7;
    }
    return data;
  };
  const origGetFloatFrequencyData = AnalyserNode.prototype.getFloatFrequencyData;
  AnalyserNode.prototype.getFloatFrequencyData = function (array) {
    origGetFloatFrequencyData.call(this, array);
    for (let i = 0; i < array.length; i++) array[i] = array[i] + jitter(i) * 1e-4;
  };

  // ── Screen / devicePixelRatio ────────────────────────────────────────────────
  for (const key of Object.keys(SCREEN)) {
    Object.defineProperty(screen, key, { get: () => SCREEN[key], configurable: true });
  }
  Object.defineProperty(window, 'devicePixelRatio', { get: () => DPR, configurable: true });

  // ── Client hints (userAgentData), coherent with the profile's UA version ─────
  const uaData = {
    brands: BRANDS,
    mobile: false,
    platform: UA_PLATFORM,
    getHighEntropyValues: (hints) =>
      Promise.resolve({
        architecture: 'x86',
        bitness: '64',
        brands: BRANDS,
        fullVersionList: FULL_VERSIONS,
        mobile: false,
        model: '',
        platform: UA_PLATFORM,
        platformVersion: '15.0.0',
        uaFullVersion: UA_FULL_VERSION,
        wow64: false,
      }),
    toJSON: () => ({ brands: BRANDS, mobile: false, platform: UA_PLATFORM }),
  };
  Object.defineProperty(navigator, 'userAgentData', { get: () => uaData, configurable: true });

  // ── WebGL2 (WebGL1 vendor/renderer are already aligned by the profile init script) ──
  if (window.WebGL2RenderingContext) {
    const origGetParameter2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function (parameter) {
      if (parameter === 37445) return WEBGL_VENDOR;    // UNMASKED_VENDOR_WEBGL
      if (parameter === 37446) return WEBGL_RENDERER;  // UNMASKED_RENDERER_WEBGL
      return origGetParameter2.call(this, parameter);
    };
  }
"""
