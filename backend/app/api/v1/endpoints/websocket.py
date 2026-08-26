from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import _resolve_org_context
from app.core.security import decode_token
from app.core.tenancy import bypass
from app.database.enums import UserStatus
from app.database.session import db_manager
from app.repositories.users import UserRepository
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

    # Re-verify LIVE status: a still-valid (unexpired) access token must not keep
    # a stream open for a user who has since been disabled, or whose org was
    # suspended/archived. Mirrors get_current_user's checks on the HTTP path.
    # (users + organizations are public tables; bypass() keeps the lookup off any
    # tenant schema.)
    try:
        async with db_manager.session_factory() as session:
            with bypass(session):
                user = await UserRepository(session).get(user_id)
            if user is None or user.status != UserStatus.active:
                await websocket.close(code=1008)
                return
            if org_id is not None:
                context = await _resolve_org_context(session, org_id)
                if context is None or context["is_deleted"] or not context["is_active"]:
                    await websocket.close(code=1008)
                    return
    except Exception:
        await websocket.close(code=1011)
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
