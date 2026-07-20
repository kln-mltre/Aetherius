"""CLI decision surface: prompt on stdin when a local run parks on a ``confirm`` step (Jalon 2-E).

``aetherius run`` executes the engine on the main thread, so the ``confirm`` handler blocks it on the
rendezvous. This sink reacts to ``input_requested`` by prompting on a **daemon thread** (questionary,
already a core dependency) and resolving the rendezvous with the answer — off the main thread, so the
mandatory timeout still frees the run if no one answers. Without a TTY there is no one to prompt, so
the request falls straight through to its timeout policy. Same rendezvous as the console modal and the
daemon route; only the surface differs.
"""

from __future__ import annotations

import sys
import threading

from ..core.events.models import EventType, RunEvent
from ..core.runtime.approvals import ApprovalGateway, Decision


class StdinApprovalSink:
    """Sink that prompts on stdin for a parked ``confirm`` and resolves the gateway with the answer.

    Structurally satisfies core.events.sinks.Sink; never raises.
    """

    def __init__(self, registry: ApprovalGateway) -> None:
        self._registry = registry

    def on_event(self, event: RunEvent) -> None:
        if event.type is not EventType.INPUT_REQUESTED:
            return
        token = event.data.get("token")
        if not token or not sys.stdin.isatty():
            return
        message = event.message or "Approve this step?"
        threading.Thread(
            target=self._prompt,
            args=(event.run_id, str(token), message),
            daemon=True,
        ).start()

    def _prompt(self, run_id: str, token: str, message: str) -> None:
        try:
            import questionary

            approved = questionary.confirm(message, default=False).ask()
        except Exception:
            return
        if approved is None:  # Ctrl-C / EOF: leave it to the timeout policy.
            return
        self._registry.resolve(run_id, token, Decision(bool(approved), decided_by="cli"))
