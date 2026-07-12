"""WebRTC leak prevention (Phase 1.5, Jalon G).

Even behind an HTTP or SOCKS proxy, a real browser can reveal its true local/public IP through WebRTC
ICE candidates — which would defeat the proxy entirely. This closes that channel so the exit IP is the
only one observable. Two levers: a Chromium launch flag forcing proxied-only UDP, and an init script
that neutralises the local-IP candidates before page scripts can read them.

Status: jalon en attente. Wired on by the network layer whenever a proxy is active (Jalon G).
"""

from __future__ import annotations

_PENDING = "Jalon 1.5-G (network): WebRTC leak prevention not implemented yet."

# Chromium args that keep WebRTC from bypassing the proxy. Applied at launch when a proxy is active.
WEBRTC_LAUNCH_FLAGS: tuple[str, ...] = (
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
)


def webrtc_leak_patch() -> str:
    """Return the init script that prevents WebRTC from exposing the real IP behind a proxy."""
    raise NotImplementedError(_PENDING)
