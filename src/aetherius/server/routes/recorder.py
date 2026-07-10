"""Endpoints to start and drive recorder sessions.

Recording is intentionally not exposed over the daemon: it is a host-local, interactive flow (a
visible browser driven by demonstration, producing a Blueprint file). Modelling that over stateless
HTTP would be a poor fit, so the endpoint is present in the contract but returns 501 and points to
the first-class paths. See docs/daemon.md.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import require_auth

router = APIRouter(prefix="/v1", tags=["recorder"], dependencies=[Depends(require_auth)])

_MESSAGE = (
    "Recording is a host-local, interactive flow and is not exposed over the daemon. "
    "Use `aetherius record` or the Console Recorder instead."
)


@router.post("/recorder/sessions", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def start_recorder() -> None:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_MESSAGE)
