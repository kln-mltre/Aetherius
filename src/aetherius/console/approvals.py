"""Console decision surface: turn an ``input_requested`` event into a modal, resolve the rendezvous.

The Console runs a Blueprint on a Textual ``@work(thread=True)`` worker. When a ``confirm`` step
parks that worker, it emits ``input_requested``; this sink — called on the worker thread — hops to the
UI thread (Textual widgets are not thread-safe) to raise a :class:`ConfirmModal`, then returns at once
so the worker can park on its rendezvous. The modal's callback resolves the shared
:class:`ApprovalGateway` when the user answers, which wakes the parked worker. Mirrors the daemon's
decisions route and the CLI stdin prompt: one rendezvous, several surfaces.
"""

from __future__ import annotations

import logging

from textual.app import App

from ..core.events.models import EventType, RunEvent
from ..core.runtime.approvals import ApprovalGateway, Decision
from .widgets.confirm import ConfirmModal

_log = logging.getLogger("aetherius.console")


class ConsoleApprovalSink:
    """Sink that raises a ConfirmModal on ``input_requested`` and resolves the gateway on the answer.

    Structurally satisfies core.events.sinks.Sink; never raises, so a UI hiccup cannot abort the run.
    """

    def __init__(self, app: App[object], registry: ApprovalGateway) -> None:
        self._app = app
        self._registry = registry

    def on_event(self, event: RunEvent) -> None:
        if event.type is not EventType.INPUT_REQUESTED:
            return
        token = event.data.get("token")
        if not token:
            return
        message = event.message or "Approve this step?"
        title = str(event.data.get("title") or "Approval required")
        try:
            # Non-blocking: schedule the modal on the UI thread and return so the worker parks on its
            # rendezvous. The modal callback resolves the gateway once the user decides.
            self._app.call_from_thread(self._prompt, event.run_id, str(token), message, title)
        except Exception:
            _log.exception("Failed to raise the approval modal for run %s.", event.run_id)

    def _prompt(self, run_id: str, token: str, message: str, title: str) -> None:
        def decided(approved: bool | None) -> None:
            self._registry.resolve(run_id, token, Decision(bool(approved), decided_by="console"))

        self._app.push_screen(
            ConfirmModal(message, title=title, confirm_label="Approve", cancel_label="Reject"),
            decided,
        )
