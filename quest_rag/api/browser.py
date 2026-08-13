"""Generic authorized browser-control API, independent of business applications."""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from quest_rag.applications.playwright_runtime import runtime
from quest_rag.auth.dependencies import require_permission
from quest_rag.auth.schemas import CurrentUser
from quest_rag.auth.service import AuthError, get_current_user_from_token

router = APIRouter(prefix="/browser", tags=["BROWSER"])


class BrowserStartRequest(BaseModel):
    url: str


class BrowserActionRequest(BaseModel):
    action: str
    target: str = ""
    value: object | None = None


def _session_user(user: CurrentUser, session_id: str):
    if not runtime.owns(session_id, user.id):
        raise HTTPException(status_code=404, detail="浏览器会话不存在")


@router.post("/sessions/start")
async def start_session(req: BrowserStartRequest, user: CurrentUser = Depends(require_permission("application.browser.connect"))):
    return await runtime.create_session(user.id, req.url)


@router.post("/sessions/{session_id}/observe")
async def observe_session(session_id: str, user: CurrentUser = Depends(require_permission("application.browser.connect"))):
    _session_user(user, session_id)
    return await runtime.observe(session_id)


@router.post("/sessions/{session_id}/action")
async def act_session(session_id: str, req: BrowserActionRequest, user: CurrentUser = Depends(require_permission("application.case.edit_self"))):
    _session_user(user, session_id)
    return await runtime.act(session_id, req.action, req.target, req.value)


@router.delete("/sessions/{session_id}")
async def close_session(session_id: str, user: CurrentUser = Depends(require_permission("application.browser.connect"))):
    _session_user(user, session_id)
    await runtime.close_session(session_id)
    return {"closed": True, "session_id": session_id}


@router.websocket("/sessions/{session_id}/live")
async def live_session(websocket: WebSocket, session_id: str):
    try:
        user = get_current_user_from_token(f"Bearer {websocket.query_params.get('token', '')}")
        if "application.browser.connect" not in user.permissions or not runtime.owns(session_id, user.id):
            await websocket.close(code=4403); return
    except AuthError:
        await websocket.close(code=4401); return
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(await runtime.observe(session_id))
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=0.8)
                if message.get("action"):
                    await websocket.send_json(await runtime.act(session_id, message["action"], message.get("target", ""), message.get("value")))
            except asyncio.TimeoutError:
                continue
    except (WebSocketDisconnect, RuntimeError):
        return
