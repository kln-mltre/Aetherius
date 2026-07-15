"""Manual in-process fire of a schedule, shared by the CLI and the Console.

``aetherius schedule run`` and the Console's "Fire now" execute a schedule immediately in the
calling process (no daemon required), with the same contract as a tick-driven fire: the outcome
lands in the durable history under the schedule's id and the alert policy applies. The schedule's
cadence (``next_run_at``/``last_run_at``) is deliberately left untouched — a manual fire must not
shift the planned slots.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence

from ...config.secrets import resolve_secrets
from ...core.blueprint.loader import load_blueprint
from ...core.errors import AetheriusError
from ...core.events.sinks import Sink
from ...core.runtime.engine import RunEngine
from ...core.runtime.result import Result
from ...store import RunRecord, Store
from ...store.models import ScheduleRecord
from .alerts import apply_notify_policy


def fire_schedule(
    record: ScheduleRecord,
    store: Store,
    *,
    sinks: Sequence[Sink] | None = None,
) -> tuple[Result, bool | None]:
    """Run *record*'s Blueprint now and return ``(result, delivered)``.

    ``delivered`` reports the alert policy outcome: True/False for sent/failed, None when the
    policy sent nothing. A Blueprint that cannot be loaded is recorded as a failed run (with the
    failure alert applied) and the underlying ``AetheriusError`` is re-raised for the caller to
    surface — same observability as a tick-driven fire, but interactive callers want the error.
    """
    secrets = resolve_secrets(record.secrets, None)
    started = datetime.now(timezone.utc)
    try:
        blueprint = load_blueprint(record.blueprint)
        result = RunEngine().run(blueprint, record.inputs, secrets, sinks=list(sinks or []))
    except AetheriusError as exc:
        store.runs.record(
            RunRecord(
                run_id=uuid.uuid4().hex,
                blueprint_name=record.blueprint,
                status="failed",
                schedule_id=record.id,
                error=str(exc),
                started_at=started,
                finished_at=datetime.now(timezone.utc),
            )
        )
        apply_notify_policy(
            record, status="failed", error=str(exc), outputs={}, secrets=secrets, store=store
        )
        raise

    store.runs.record(
        RunRecord(
            run_id=result.run_id,
            blueprint_name=result.blueprint_name,
            status=result.status.value,
            schedule_id=record.id,
            error=result.error,
            outputs=result.outputs,
            started_at=result.started_at,
            finished_at=result.finished_at,
        )
    )
    delivered = apply_notify_policy(
        record,
        status=result.status.value,
        error=result.error,
        outputs=result.outputs,
        secrets=secrets,
        store=store,
    )
    return result, delivered
