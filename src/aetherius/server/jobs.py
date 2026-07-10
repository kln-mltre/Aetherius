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
from typing import Any, Callable, Mapping

from ..core.blueprint.models import Blueprint
from ..core.errors import AetheriusError
from ..core.events.models import RunEvent
from ..core.runtime.engine import RunEngine
from ..core.runtime.result import Result
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
    status: DaemonRunStatus = "queued"
    history: list[RunEvent] = field(default_factory=list)
    subscribers: set[asyncio.Queue[RunEvent | None]] = field(default_factory=set)
    result: Result | None = None
    error: str | None = None
    finished: asyncio.Event = field(default_factory=asyncio.Event)


class RunManager:
    """In-memory registry of runs and their event streams for the lifetime of the daemon."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        # The loop only keeps weak references to tasks; hold strong ones so a run cannot be
        # garbage-collected mid-flight while it awaits the worker thread.
        self._tasks: set[asyncio.Task[None]] = set()

    def get(self, run_id: str) -> Job | None:
        return self._jobs.get(run_id)

    async def submit(
        self,
        blueprint: Blueprint,
        inputs: Mapping[str, Any] | None,
        secrets: Mapping[str, str] | None,
    ) -> str:
        """Register a run and start it in the background, returning its id immediately."""
        run_id = uuid.uuid4().hex
        job = Job(run_id=run_id)
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
        for queue in list(job.subscribers):
            queue.put_nowait(event)

    async def _execute(
        self,
        job: Job,
        blueprint: Blueprint,
        inputs: Mapping[str, Any] | None,
        secrets: Mapping[str, str] | None,
        sink: QueueSink,
    ) -> None:
        job.status = "running"
        try:
            result = await asyncio.to_thread(
                RunEngine().run,
                blueprint,
                inputs,
                secrets,
                sinks=[sink],
                run_id=job.run_id,
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
            job.finished.set()
            for queue in list(job.subscribers):
                queue.put_nowait(None)  # sentinel: end of stream

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
