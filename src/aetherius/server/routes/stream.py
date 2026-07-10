"""WebSocket endpoint streaming a run event feed.

On connect the manager hands back a queue pre-loaded with the run's retained history, then fed live
events until the run finishes. This makes the stream reliable regardless of when the client connects:
early, mid-run, or after completion (it simply replays and closes). Each frame conforms to
contracts/events.schema.json.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from ..deps import get_config, get_manager, websocket_authorized
from ..schemas import event_to_wire

router = APIRouter()

_CLOSE_POLICY = 1008  # WebSocket "policy violation": unauthorized or unknown run.


@router.websocket("/v1/runs/{run_id}/events")
async def stream_run_events(websocket: WebSocket, run_id: str) -> None:
    config = get_config(websocket)
    manager = get_manager(websocket)

    await websocket.accept()

    if not websocket_authorized(
        config,
        websocket.headers.get("Authorization"),
        websocket.query_params.get("token"),
    ):
        await websocket.close(code=_CLOSE_POLICY)
        return

    queue = manager.subscribe(run_id)
    if queue is None:
        await websocket.close(code=_CLOSE_POLICY)
        return

    try:
        while True:
            event = await queue.get()
            if event is None:  # sentinel: run finished, stream exhausted
                break
            await websocket.send_json(event_to_wire(event))
    except WebSocketDisconnect:
        pass
    finally:
        manager.unsubscribe(run_id, queue)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()
