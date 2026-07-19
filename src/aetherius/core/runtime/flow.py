"""Flow actions (``if``/``repeat``/``for_each``): interpreted before any driver sees them.

Split out of the step executor (steps.py), which re-enters itself through the ``FlowHost``
protocol for the nested lists — so every Act inherits the flow semantics without wiring
anything, and the executor file stays focused on the pipeline itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Protocol, Sequence

from pydantic import ValidationError

from ..blueprint.models import StepModel
from ..errors import ActionError

if TYPE_CHECKING:
    from .context import RunContext

_TRUTHY: frozenset[str] = frozenset({"true", "1", "yes"})

# Template context names a for_each loop variable would shadow (see RunContext.template_ctx).
_RESERVED_NAMES: frozenset[str] = frozenset({"inputs", "secrets", "vars", "env", "steps"})

_DEFAULT_LOOP_VAR = "item"


def is_truthy(value: Any) -> bool:
    """Single truthiness rule shared by ``assert`` conditions and ``when`` guards."""
    return str(value).strip().lower() in _TRUTHY


class FlowHost(Protocol):
    """The slice of the executor a flow action needs: recursion plus the run scope."""

    ctx: "RunContext"

    def run(self, steps: Sequence[StepModel], path: str = "", act: str | None = None) -> None: ...


def run_flow(
    host: FlowHost,
    step: StepModel,
    renderer: Callable[[Any], Any],
    path: str,
    act: str,
) -> dict[str, Any]:
    """Interpret one flow step; nested lists re-enter *host* with the step's effective *act*."""
    if step.action == "if":
        return _flow_if(host, step, renderer, path, act)
    if step.action == "repeat":
        return _flow_repeat(host, step, renderer, path, act)
    return _flow_for_each(host, step, renderer, path, act)


def _flow_if(
    host: FlowHost, step: StepModel, renderer: Callable[[Any], Any], path: str, act: str
) -> dict[str, Any]:
    p = step.extra_fields
    if "condition" not in p:
        raise ActionError(f"if: missing required parameter 'condition' (step {path!r}).")
    branch = "then" if is_truthy(renderer(p["condition"])) else "else"
    if branch == "else" and "else" not in p:
        return {"branch": None}
    host.run(_nested_steps(step, branch, path), path, act)
    return {"branch": branch}


def _flow_repeat(
    host: FlowHost, step: StepModel, renderer: Callable[[Any], Any], path: str, act: str
) -> dict[str, Any]:
    p = step.extra_fields
    if "times" not in p:
        raise ActionError(f"repeat: missing required parameter 'times' (step {path!r}).")
    times = _coerce_times(renderer(p["times"]), path)
    nested = _nested_steps(step, "steps", path)
    for i in range(times):
        host.run(nested, f"{path}[{i}]", act)
    return {"iterations": times}


def _flow_for_each(
    host: FlowHost, step: StepModel, renderer: Callable[[Any], Any], path: str, act: str
) -> dict[str, Any]:
    p = step.extra_fields
    if "items" not in p:
        raise ActionError(f"for_each: missing required parameter 'items' (step {path!r}).")
    items = renderer(p["items"])
    if not isinstance(items, (list, tuple)):
        raise ActionError(
            f"for_each: 'items' must render to a list, got {type(items).__name__} (step {path!r})."
        )
    var = p.get("as", _DEFAULT_LOOP_VAR)
    if not isinstance(var, str) or not var.isidentifier():
        raise ActionError(
            f"for_each: 'as' must be a valid identifier, got {var!r} (step {path!r})."
        )
    if var in _RESERVED_NAMES:
        raise ActionError(
            f"for_each: loop variable {var!r} would shadow a reserved "
            f"template name (step {path!r})."
        )
    nested = _nested_steps(step, "steps", path)

    # Save and restore whatever the variable shadowed so nested loops compose.
    missing = object()
    previous = host.ctx.scope.get(var, missing)
    try:
        for i, item in enumerate(items):
            host.ctx.scope[var] = item
            host.run(nested, f"{path}[{i}]", act)
    finally:
        if previous is missing:
            host.ctx.scope.pop(var, None)
        else:
            host.ctx.scope[var] = previous
    return {"iterations": len(items)}


def _nested_steps(step: StepModel, key: str, path: str) -> list[StepModel]:
    raw = step.extra_fields.get(key)
    if not isinstance(raw, list):
        raise ActionError(f"{step.action}: '{key}' must be a list of steps (step {path!r}).")
    try:
        return [StepModel.model_validate(item) for item in raw]
    except ValidationError as exc:
        raise ActionError(f"{step.action}: invalid step in '{key}' (step {path!r}): {exc}") from exc


def _coerce_times(value: Any, path: str) -> int:
    times: int | None = None
    if isinstance(value, int) and not isinstance(value, bool):
        times = value
    elif isinstance(value, str):
        try:
            times = int(value.strip())
        except ValueError:
            times = None
    if times is None:
        raise ActionError(f"repeat: 'times' must be an integer, got {value!r} (step {path!r}).")
    if times < 0:
        raise ActionError(f"repeat: 'times' must be >= 0, got {times} (step {path!r}).")
    return times
