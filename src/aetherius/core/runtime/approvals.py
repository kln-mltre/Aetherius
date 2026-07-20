"""Human-in-the-loop rendezvous: park a run until a human decides (Jalon 2-E).

The ``confirm`` action (acts/_shared.py) runs on a worker thread — ``asyncio.to_thread`` in the
daemon, a Textual ``@work(thread=True)`` worker in the Console, the main thread for ``aetherius
run``. It reaches its decision surface through an :class:`ApprovalGateway` carried on the
:class:`~aetherius.core.runtime.context.RunContext`. The surface (daemon route, console modal, CLI
prompt, ntfy button) signals the parked worker by resolving the request.

Blocking wait, not suspend/resume: the run — its browser included — stays alive and parked on a
``threading.Event``. That primitive is already cross-thread safe, so a surface running on the asyncio
loop resolves it directly, without a ``call_soon_threadsafe`` hop (the deliberate simplification over
QueueSink's thread->loop bridge, which exists because a Textual widget is *not* thread-safe; an Event
is). The mandatory timeout guarantees a parked run is always eventually freed.
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ApprovalRequest:
    """One pending human decision: the message shown, and the opaque token that authorises a reply.

    The token is bound to ``run_id`` so a decision for one run can never resolve another; a surface
    must present both to resolve the rendezvous.
    """

    run_id: str
    token: str
    message: str
    step_id: str | None = None
    title: str | None = None
    timeout_ms: float | None = None

    @staticmethod
    def create(
        run_id: str,
        message: str,
        *,
        step_id: str | None = None,
        title: str | None = None,
        timeout_ms: float | None = None,
    ) -> "ApprovalRequest":
        return ApprovalRequest(
            run_id=run_id,
            token=secrets.token_urlsafe(16),
            message=message,
            step_id=step_id,
            title=title,
            timeout_ms=timeout_ms,
        )


@dataclass(frozen=True)
class Decision:
    """A human's answer to an :class:`ApprovalRequest`.

    ``value`` carries an optional supplied value (the "provide a value" case); ``decided_by`` records
    which surface answered (``console``/``api``/``cli``/``notification``/``timeout``) for the trace.
    """

    approved: bool
    value: Any = None
    decided_by: str | None = None


@dataclass
class Rendezvous:
    """The waiter a parked worker blocks on until a decision arrives or the deadline passes."""

    request: ApprovalRequest
    _event: threading.Event = field(default_factory=threading.Event)
    _decision: Decision | None = None

    def wait(self, timeout_s: float | None) -> Decision | None:
        """Block until resolved, returning the :class:`Decision`, or ``None`` on timeout."""
        if self._event.wait(timeout_s):
            return self._decision
        return None

    def _resolve(self, decision: Decision) -> None:
        # First writer wins: a late second decision (e.g. a notification tap after the console modal)
        # is a no-op, never a double-apply.
        if not self._event.is_set():
            self._decision = decision
            self._event.set()


class ApprovalGateway(Protocol):
    """The decision channel a run consults for its ``confirm`` steps.

    ``None`` on the RunContext means *unattended*: no surface is listening, so ``confirm`` applies its
    ``on_timeout`` policy at once instead of parking forever.
    """

    def open(self, request: ApprovalRequest) -> Rendezvous: ...

    def close(self, request: ApprovalRequest) -> None: ...

    def resolve(self, run_id: str, token: str, decision: Decision) -> bool: ...

    def notification_data(self, request: ApprovalRequest) -> dict[str, Any]: ...


class ApprovalRegistry:
    """In-memory rendezvous registry keyed by ``run_id`` (the default gateway).

    Thread-safe: the worker thread registers a request while a surface thread (asyncio loop, Textual
    UI, a prompt thread) resolves it. A run parks at most one ``confirm`` at a time, so one slot per
    ``run_id`` is enough. Used directly by the Console and the CLI; the daemon subclasses it to attach
    remote-callback context (server/jobs.py).
    """

    def __init__(self) -> None:
        self._pending: dict[str, Rendezvous] = {}
        self._lock = threading.Lock()

    def open(self, request: ApprovalRequest) -> Rendezvous:
        rv = Rendezvous(request=request)
        with self._lock:
            self._pending[request.run_id] = rv
        return rv

    def close(self, request: ApprovalRequest) -> None:
        with self._lock:
            current = self._pending.get(request.run_id)
            if current is not None and current.request.token == request.token:
                del self._pending[request.run_id]

    def resolve(self, run_id: str, token: str, decision: Decision) -> bool:
        """Signal the parked worker for ``run_id``; return False for an unknown run or token.

        The token check is the authorisation: a decision must carry the exact opaque token minted for
        the request. A stale or forged token resolves nothing.
        """
        with self._lock:
            rv = self._pending.get(run_id)
            if rv is None or rv.request.token != token:
                return False
        rv._resolve(decision)
        return True

    def pending(self, run_id: str) -> ApprovalRequest | None:
        with self._lock:
            rv = self._pending.get(run_id)
            return rv.request if rv is not None else None

    def notification_data(self, request: ApprovalRequest) -> dict[str, Any]:
        """Deep-link context for a notification (empty here; the daemon gateway fills it in)."""
        return {}
