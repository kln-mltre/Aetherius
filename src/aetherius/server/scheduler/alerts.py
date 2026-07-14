"""Per-schedule alert policy: turn a fired run's outcome into a notification.

The notify layer stays stateless by design (docs/notifications.md § Déduplication); the scheduler
owns the policy because it owns the state scope (the schedule id). A schedule's ``notify`` dict is
``{"channel", "target"?, "config"?, "on"?}`` where ``on`` is ``failure`` (default), ``success``,
``always`` or ``change`` — the latter alerts only when the run's outputs differ from the previous
fire, via ``StateRepository.compare_and_set``. ``target``/``config`` values may reference
``{{ secrets.x }}``, rendered at fire time with the schedule's resolved secrets, so channel
addresses are never persisted.
"""

from __future__ import annotations

import json
import logging
from pathlib import PurePath
from typing import Any, Literal, Mapping

from ...core.blueprint.template import render_value
from ...core.errors import AetheriusError, ScheduleError
from ...core.runtime.result import RunStatus
from ...notify import Notification, NotificationChannel, NotificationLevel, dispatch
from ...notify.registry import build_channel, known_kinds, target_key
from ...store import Store
from ...store.models import ScheduleRecord

NotifyOn = Literal["failure", "success", "always", "change"]

_NOTIFY_ON_VALUES: tuple[str, ...] = ("failure", "success", "always", "change")

# Key under the schedule-id scope holding the last successful outputs (the "change" baseline).
_STATE_KEY = "outputs"

_log = logging.getLogger("aetherius.scheduler")


def validate_notify_policy(data: Mapping[str, Any]) -> None:
    """Reject a malformed notify policy at schedule-creation time (empty dict = no alerts).

    Shape and channel kind are checked here; the config keys themselves (webhook url, bot token)
    are validated by ``build_channel`` at fire time, once secrets are resolvable.

    Raises:
        ScheduleError: missing or unknown channel, unknown ``on`` value, non-object ``config``.
    """
    if not data:
        return
    kind = data.get("channel")
    if not kind:
        raise ScheduleError("Notify policy requires a 'channel' (webhook, discord, telegram, ...).")
    if kind not in known_kinds():
        known = ", ".join(known_kinds())
        raise ScheduleError(f"Unknown notification channel {kind!r}. Known channels: {known}.")
    on = data.get("on", "failure")
    if on not in _NOTIFY_ON_VALUES:
        allowed = ", ".join(_NOTIFY_ON_VALUES)
        raise ScheduleError(f"Unknown notify policy 'on' {on!r}; expected one of: {allowed}.")
    config = data.get("config", {})
    if not isinstance(config, Mapping):
        raise ScheduleError(
            f"Notify policy 'config' must be an object, got {type(config).__name__}."
        )


def apply_notify_policy(
    record: ScheduleRecord,
    *,
    status: str,
    error: str | None,
    outputs: dict[str, Any],
    secrets: Mapping[str, str],
    store: Store,
) -> bool | None:
    """Send the schedule's alert for one finished run, per its ``on`` policy.

    Returns True/False for delivered/failed, or None when the policy sent nothing. Never raises:
    an alerting failure (unresolvable secret, broken channel config, delivery error) is logged and
    contained — it must not take the tick loop or the CLI fire down with it.
    """
    policy = record.notify
    if not policy:
        return None
    failed = status != RunStatus.SUCCESS.value
    on = str(policy.get("on", "failure"))

    if on == "failure" and not failed:
        return None
    if on == "success" and failed:
        return None
    if on == "change":
        # Failures neither alert nor move the baseline: a transient error must not turn the next
        # successful run into a false "change" alert.
        if failed:
            return None
        fingerprint = json.dumps(outputs, sort_keys=True, default=str)
        if not store.state.compare_and_set(record.id, _STATE_KEY, fingerprint):
            return None

    try:
        channel = _build_channel(policy, secrets)
    except AetheriusError:
        _log.exception("Schedule %s: cannot build notify channel; alert dropped.", record.id)
        return False
    return dispatch(_notification(record, status=status, error=error, outputs=outputs), channel)


def _build_channel(policy: Mapping[str, Any], secrets: Mapping[str, str]) -> NotificationChannel:
    """Render ``{{ secrets.x }}`` references and build the channel (same seam as the notify step)."""
    ctx = {"secrets": dict(secrets)}
    kind = str(policy.get("channel", ""))
    config = {str(k): str(render_value(v, ctx)) for k, v in dict(policy.get("config", {})).items()}
    target = policy.get("target")
    if target:
        key = target_key(kind)
        if key is not None:
            config.setdefault(key, str(render_value(target, ctx)))
    return build_channel(kind, config)


def _notification(
    record: ScheduleRecord,
    *,
    status: str,
    error: str | None,
    outputs: dict[str, Any],
) -> Notification:
    failed = status != RunStatus.SUCCESS.value
    # Basename only: the stored blueprint is usually an absolute path, noise in an alert.
    lines = [f"{PurePath(record.blueprint).name}: run {status}"]
    if error:
        lines.append(error)
    if outputs and not failed:
        digest = json.dumps(outputs, ensure_ascii=False, default=str)
        lines.append(digest if len(digest) <= 500 else digest[:500] + "…")
    return Notification(
        body="\n".join(lines),
        title=f"Aetherius — schedule {record.name}",
        level=NotificationLevel.ERROR if failed else NotificationLevel.INFO,
        data={"schedule_id": record.id, "status": status},
    )
