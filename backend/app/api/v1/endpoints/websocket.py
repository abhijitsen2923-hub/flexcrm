from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.services.realtime import realtime_manager


router = APIRouter()


@router.websocket("/updates")
async def websocket_updates(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise ValueError("invalid token type")
        user_id = UUID(payload["sub"])
        # Tag the socket with its org so it only receives that org's broadcasts.
        org_raw = payload.get("org")
        org_id = UUID(org_raw) if org_raw else None
    except Exception:
        await websocket.close(code=1008)
        return

    last_event_id = _parse_last_event_id(websocket.query_params.get("last_event_id"))

    await realtime_manager.connect(websocket, user_id, org_id=org_id, last_event_id=last_event_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        # Always deregister — not just on a clean WebSocketDisconnect. Any other
        # exit (receive error, cancellation) must not leak the socket.
        realtime_manager.disconnect(websocket, user_id)


def _parse_last_event_id(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 0 else None
