"""WebRTC leak prevention (Phase 1.5, Jalon G).

Even behind an HTTP or SOCKS proxy, a real browser can reveal its true local/public IP through WebRTC
ICE candidates — which would defeat the proxy entirely. This closes that channel so the exit IP is the
only one observable. Two levers: a Chromium launch flag forcing proxied-only UDP, and an init script
that neutralises the local-IP candidates before page scripts can read them.

Status: wired on by the network layer whenever a proxy is active (Jalon G).
"""

from __future__ import annotations

# Chromium args that keep WebRTC from bypassing the proxy. Applied at launch when a proxy is active.
WEBRTC_LAUNCH_FLAGS: tuple[str, ...] = (
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
)

# Init script: wrap RTCPeerConnection so ICE candidates that expose a local ("typ host"), reflexive
# ("typ srflx") or mDNS (".local") address never reach page scripts. The launch flag does the heavy
# lifting; this is defense in depth for the property- and listener-style candidate handlers alike. A
# window marker makes the guard observable from a test without any network round trip.
_WEBRTC_LEAK_PATCH_JS = """
(() => {
  const OrigPC = window.RTCPeerConnection || window.webkitRTCPeerConnection;
  if (!OrigPC) return;
  window.__aetherius_webrtc_guard = true;

  const LEAKY = /(?:\\btyp host\\b|\\btyp srflx\\b|\\.local\\b)/i;
  const isLeaky = (candidate) => !!candidate && LEAKY.test(candidate.candidate || '');
  const filter = (handler) => function (event) {
    if (event && isLeaky(event.candidate)) return undefined;
    return handler.apply(this, arguments);
  };

  const Patched = function (...args) {
    const pc = new OrigPC(...args);
    Object.defineProperty(pc, 'onicecandidate', {
      configurable: true,
      get() { return this.__aetherius_onicecandidate || null; },
      set(fn) { this.__aetherius_onicecandidate = typeof fn === 'function' ? filter(fn) : fn; },
    });
    const addEventListener = pc.addEventListener.bind(pc);
    pc.addEventListener = function (type, listener, ...rest) {
      if (type === 'icecandidate' && typeof listener === 'function') {
        return addEventListener(type, filter(listener), ...rest);
      }
      return addEventListener(type, listener, ...rest);
    };
    return pc;
  };
  Patched.prototype = OrigPC.prototype;
  if (OrigPC.generateCertificate) {
    Patched.generateCertificate = OrigPC.generateCertificate.bind(OrigPC);
  }

  window.RTCPeerConnection = Patched;
  if (window.webkitRTCPeerConnection) window.webkitRTCPeerConnection = Patched;
})();
"""


def webrtc_leak_patch() -> str:
    """Return the init script that prevents WebRTC from exposing the real IP behind a proxy."""
    return _WEBRTC_LEAK_PATCH_JS
