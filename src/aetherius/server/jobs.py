"""Asynchronous run manager tracking in-flight runs and their event streams.

``RunEngine.run()`` is synchronous and blocking, so each run executes on a worker thread while the
daemon stays responsive. Events cross back from that thread to the event loop through
``loop.call_soon_threadsafe`` — the same thread-to-loop bridge the Console uses (see
``docs/console.md`` § pattern Sink), here feeding an in-memory history plus any live WebSocket
subscribers instead of a Textual widget.

All job-state mutation (history, subscribers, status) happens on the loop thread; the only thing the
worker thread touches is ``call_soon_threadsafe``. That single-threaded discipline is why no locks
are needed: ``subscribe`` snapshots the retained history and registers atomically, with no ``await``
in between, so no event can slip past a joining subscriber.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from ..core.blueprint.models import Blueprint
from ..core.errors import AetheriusError
from ..core.events.models import EventType, RunEvent
from ..core.runtime.approvals import ApprovalGateway, ApprovalRegistry, Decision
from ..core.runtime.engine import RunEngine
from ..core.runtime.result import Result
from ..store import ApprovalRepository, RunRecord, RunRepository
from .schemas import DaemonRunStatus, to_daemon_status


class QueueSink:
    """Event sink that forwards each RunEvent from the worker thread onto the event loop.

    Structurally satisfies ``core.events.sinks.Sink``. Never raises: a streaming failure must not
    abort the run it is merely observing.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, ingest: Callable[[RunEvent], None]) -> None:
        self._loop = loop
        self._ingest = ingest

    def on_event(self, event: RunEvent) -> None:
        try:
            self._loop.call_soon_threadsafe(self._ingest, event)
        except RuntimeError:
            # The loop is closed (daemon shutting down); there is nothing left to stream to.
            pass


@dataclass
class Job:
    """A single run: its status, retained event history, and live subscriber queues."""

    run_id: str
    # Set when the run was fired by a schedule (Jalon D); ties the history back to it.
    schedule_id: str | None = None
    status: DaemonRunStatus = "queued"
    history: list[RunEvent] = field(default_factory=list)
    subscribers: set[asyncio.Queue[RunEvent | None]] = field(default_factory=set)
    result: Result | None = None
    error: str | None = None
    finished: asyncio.Event = field(default_factory=asyncio.Event)


class RunManager:
    """In-memory registry of runs and their event streams for the lifetime of the daemon.

    Live event streams stay in memory (they only matter while a run is in flight), but each run's
    final outcome graduates onto the durable store (Jalon A) so history survives a restart. The
    ``runs`` repository is optional: passing ``None`` keeps the manager purely in-memory, which is how
    the unit tests drive it.
    """

    def __init__(
        self,
        runs: RunRepository | None = None,
        *,
        approvals: ApprovalRepository | None = None,
        registry: ApprovalGateway | None = None,
    ) -> None:
        self._runs = runs
        self._approvals = approvals
        # The rendezvous a parked ``confirm`` blocks on; the decisions route resolves it (Jalon 2-E).
        self._registry: ApprovalGateway = registry or ApprovalRegistry()
        self._jobs: dict[str, Job] = {}
        # The loop only keeps weak references to tasks; hold strong ones so a run cannot be
        # garbage-collected mid-flight while it awaits the worker thread.
        self._tasks: set[asyncio.Task[None]] = set()

    def get(self, run_id: str) -> Job | None:
        return self._jobs.get(run_id)

    def resolve_decision(self, run_id: str, token: str, decision: Decision) -> bool:
        """Deliver a human decision to a parked ``confirm``; False for an unknown run or token."""
        return self._registry.resolve(run_id, token, decision)

    async def submit(
        self,
        blueprint: Blueprint,
        inputs: Mapping[str, Any] | None,
        secrets: Mapping[str, str] | None,
        *,
        schedule_id: str | None = None,
    ) -> str:
        """Register a run and start it in the background, returning its id immediately.

        ``schedule_id`` marks a run fired by the scheduler; it flows into the persisted history
        but changes nothing else — a scheduled run is indistinguishable from a manual one.
        """
        run_id = uuid.uuid4().hex
        job = Job(run_id=run_id, schedule_id=schedule_id)
        self._jobs[run_id] = job

        loop = asyncio.get_running_loop()
        sink = QueueSink(loop, lambda event: self._ingest(run_id, event))
        task = asyncio.create_task(self._execute(job, blueprint, inputs, secrets, sink))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run_id

    def _ingest(self, run_id: str, event: RunEvent) -> None:
        """Runs on the loop thread: retain the event and fan it out to live subscribers."""
        job = self._jobs.get(run_id)
        if job is None:
            return
        job.history.append(event)
        self._persist_approval(event)
        for queue in list(job.subscribers):
            queue.put_nowait(event)

    def _persist_approval(self, event: RunEvent) -> None:
        """Mirror a confirm request and its resolution onto the store's audit trail (best-effort).

        Driven off the authoritative event stream — ``input_provided`` carries the true final outcome
        whether a human decided or the timeout fired — so there is a single, race-free writer. The
        write is tiny and only runs for the two rare confirm events, so doing it inline on the loop is
        fine.
        """
        if self._approvals is None:
            return
        token = event.data.get("token")
        if not token:
            return
        try:
            if event.type == EventType.INPUT_REQUESTED:
                self._approvals.open_pending(
                    str(token), event.run_id, event.message or "", step_id=event.step_id
                )
            elif event.type == EventType.INPUT_PROVIDED:
                decided_by = event.data.get("decided_by")
                status = (
                    "timeout"
                    if decided_by == "timeout"
                    else ("approved" if event.data.get("approved") else "rejected")
                )
                self._approvals.resolve(str(token), status, decided_by=decided_by)
        except Exception:  # noqa: BLE001 - audit trail is best-effort; never disturb the run
            pass

    async def _execute(
        self,
        job: Job,
        blueprint: Blueprint,
        inputs: Mapping[str, Any] | None,
        secrets: Mapping[str, str] | None,
        sink: QueueSink,
    ) -> None:
        job.status = "running"
        started = datetime.now(timezone.utc)
        try:
            result = await asyncio.to_thread(
                RunEngine().run,
                blueprint,
                inputs,
                secrets,
                sinks=[sink],
                run_id=job.run_id,
                approvals=self._registry,
            )
            job.result = result
            job.status = to_daemon_status(result.status)
            job.error = result.error
        except AetheriusError as exc:
            # Validation and unexpected engine failures surface here; never leave a job "running".
            job.status = "failed"
            job.error = str(exc)
        except Exception as exc:  # noqa: BLE001 - last resort so a crash still closes the stream
            job.status = "failed"
            job.error = str(exc)
        finally:
            # Persist the outcome before closing the stream so a consumer that saw the run finish can
            # already read it back. The store access runs off the loop and never aborts the run.
            await self._persist(job, blueprint, started)
            job.finished.set()
            for queue in list(job.subscribers):
                queue.put_nowait(None)  # sentinel: end of stream

    async def _persist(self, job: Job, blueprint: Blueprint, started: datetime) -> None:
        """Graduate a finished run's outcome onto the durable store, off the event loop."""
        if self._runs is None:
            return
        try:
            await asyncio.to_thread(self._runs.record, _to_run_record(job, blueprint, started))
        except Exception:  # noqa: BLE001 - history is best-effort; never fail or stall a run over it
            pass

    def subscribe(self, run_id: str) -> asyncio.Queue[RunEvent | None] | None:
        """Return a queue pre-loaded with the retained history, then fed live events.

        ``None`` if the run is unknown. If the run has already finished, the queue ends with a
        ``None`` sentinel right after the replay so the caller closes cleanly.
        """
        job = self._jobs.get(run_id)
        if job is None:
            return None
        queue: asyncio.Queue[RunEvent | None] = asyncio.Queue()
        for event in job.history:
            queue.put_nowait(event)
        if job.finished.is_set():
            queue.put_nowait(None)
        else:
            job.subscribers.add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[RunEvent | None]) -> None:
        job = self._jobs.get(run_id)
        if job is not None:
            job.subscribers.discard(queue)


def _to_run_record(job: Job, blueprint: Blueprint, started: datetime) -> RunRecord:
    """Build the durable record from a finished job.

    A successful (or partial) run carries a full :class:`Result` to draw from; a run that failed
    before producing one falls back to the Blueprint name and the captured start time.
    """
    if job.result is not None:
        result = job.result
        return RunRecord(
            run_id=job.run_id,
            blueprint_name=result.blueprint_name,
            status=result.status.value,
            schedule_id=job.schedule_id,
            error=result.error,
            outputs=result.outputs,
            started_at=result.started_at,
            finished_at=result.finished_at,
        )
    return RunRecord(
        run_id=job.run_id,
        blueprint_name=blueprint.name,
        status="failed",
        schedule_id=job.schedule_id,
        error=job.error,
        started_at=started,
        finished_at=datetime.now(timezone.utc),
    )
