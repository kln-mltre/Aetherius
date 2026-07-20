"""Run endpoints: submit a Blueprint and fetch run status and results."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ...core.blueprint.loader import load_blueprint, validate_blueprint_data
from ...core.blueprint.models import Blueprint
from ...core.errors import BlueprintError
from ...core.runtime.approvals import Decision
from ..deps import get_manager, require_auth
from ..jobs import RunManager
from ..schemas import DecisionAck, DecisionRequest, Run, RunHandle, RunRequest

router = APIRouter(prefix="/v1", tags=["runs"], dependencies=[Depends(require_auth)])


def _resolve_blueprint(ref: dict[str, object] | str) -> Blueprint:
    """Turn the request's Blueprint reference into a validated model.

    A string is a path the daemon resolves from disk; an object is validated in memory. Structural
    problems fail fast here (422); semantic ones (unsupported Act, missing input) surface at run
    time as a failed run, mirroring the in-process behaviour.
    """
    try:
        if isinstance(ref, str):
            return load_blueprint(ref)
        return validate_blueprint_data(ref)
    except BlueprintError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED, response_model=RunHandle)
async def create_run(body: RunRequest, manager: RunManager = Depends(get_manager)) -> RunHandle:
    blueprint = _resolve_blueprint(body.blueprint)
    run_id = await manager.submit(blueprint, body.inputs, body.secrets)
    return RunHandle(run_id=run_id)


@router.get("/runs/{run_id}", response_model=Run)
async def get_run(run_id: str, manager: RunManager = Depends(get_manager)) -> Run:
    job = manager.get(run_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown run {run_id!r}."
        )
    outputs = job.result.outputs if job.result is not None else {}
    return Run(run_id=run_id, status=job.status, outputs=outputs, error=job.error)


@router.post("/runs/{run_id}/decisions", response_model=DecisionAck)
async def decide_run(
    run_id: str, body: DecisionRequest, manager: RunManager = Depends(get_manager)
) -> DecisionAck:
    """Deliver a human decision to a run parked on a ``confirm`` step (Jalon 2-E).

    404 when the run is unknown; 409 when nothing is awaiting a decision or the token does not match
    (the opaque token is the authorisation, bound to this run). The run keeps running throughout.
    """
    if manager.get(run_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown run {run_id!r}."
        )
    decision = Decision(approved=body.approved, value=body.value, decided_by="api")
    if not manager.resolve_decision(run_id, body.token, decision):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No pending decision for this run, or the token is invalid.",
        )
    return DecisionAck(run_id=run_id, accepted=True)
