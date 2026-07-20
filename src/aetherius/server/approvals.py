"""Daemon-flavoured approval gateway: the in-memory rendezvous plus remote-callback context.

Identical rendezvous mechanics as the base :class:`ApprovalRegistry` (a parked worker blocks on a
``threading.Event``, resolved here by the decisions route). The one addition is
:meth:`notification_data`: when the daemon knows a publicly reachable URL, a ``confirm`` notification
carries the decision route + token so a surface that supports interactive responses (an ntfy action
button) can approve or reject with a single tap. Persistence of the audit trail is handled by the
RunManager off the event stream, not here — this stays a pure rendezvous.
"""

from __future__ import annotations

from typing import Any

from ..core.runtime.approvals import ApprovalRegistry, ApprovalRequest


class DaemonApprovalRegistry(ApprovalRegistry):
    """Approval registry that can hand a notification the daemon's decision callback."""

    def __init__(self, *, public_url: str | None = None, token: str | None = None) -> None:
        super().__init__()
        self._public_url = public_url.rstrip("/") if public_url else None
        self._token = token

    def notification_data(self, request: ApprovalRequest) -> dict[str, Any]:
        """Deep-link context for a confirm notification, or ``{}`` when no public URL is set.

        Without a reachable URL (the loopback default) the buttons would be dead, so the alert stays
        purely informational — the honest behaviour rather than a broken action.
        """
        if self._public_url is None:
            return {}
        confirm: dict[str, Any] = {
            "decisions_url": f"{self._public_url}/v1/runs/{request.run_id}/decisions",
            "token": request.token,
        }
        if self._token:
            confirm["auth"] = f"Bearer {self._token}"
        return {"confirm": confirm}
