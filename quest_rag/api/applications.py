import asyncio
from fastapi import APIRouter, Depends, File, Form, UploadFile, WebSocket, WebSocketDisconnect

from quest_rag.applications import definitions, service
from quest_rag.applications.schemas import BrowserActionRequest, BrowserConnectRequest, CaseCreateRequest, CaseIdRequest, DraftFieldUpdateRequest, SyncRequest, SubmitRequest, WorkflowActionRequest
from quest_rag.applications.playwright_runtime import runtime
from quest_rag.applications import workflow_service
from quest_rag.auth.dependencies import require_permission
from quest_rag.auth.schemas import CurrentUser
from quest_rag.auth.service import get_current_user_from_token, AuthError

router = APIRouter(prefix="/applications", tags=["APPLICATIONS"])


@router.post("/definitions/list")
def list_application_definitions(current_user: CurrentUser = Depends(require_permission("application.case.read_self"))):
    return definitions.list_definitions()


@router.post("/cases/create")
def create_application_case(req: CaseCreateRequest, current_user: CurrentUser = Depends(require_permission("application.case.create"))):
    return service.create_application(current_user, req.business_code)


@router.post("/cases/list")
def list_application_cases(current_user: CurrentUser = Depends(require_permission("application.case.read_self"))):
    return service.list_application_cases(current_user)


@router.post("/cases/get")
def get_application_case(req: CaseIdRequest, current_user: CurrentUser = Depends(require_permission("application.case.read_self"))):
    return service.get_application_detail(current_user, req.case_id)


@router.post("/drafts/update-field")
def update_application_draft_field(req: DraftFieldUpdateRequest, current_user: CurrentUser = Depends(require_permission("application.case.edit_self"))):
    return service.update_draft_field(current_user, req.case_id, req.field_key, req.value, req.expected_revision)


@router.post("/materials/upload")
async def upload_application_material(
    case_id: str = Form(...),
    material_key: str = Form(...),
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission("application.case.edit_self")),
):
    return service.upload_material(current_user, case_id, material_key, file.filename or "未命名材料", file.content_type, await file.read())


@router.post("/browser/connect")
async def connect_application_browser(req: BrowserConnectRequest, current_user: CurrentUser = Depends(require_permission("application.browser.connect"))):
    result = service.connect_browser(current_user, req.case_id, req.device_name)
    detail = service.get_application_detail(current_user, req.case_id)
    if detail.get("execution_mode") == "playwright":
        values = {field["key"]: field["value"] for field in detail["fields"] if field.get("value") is not None}
        observed = await runtime.start(req.case_id, result["entry_url"], values, owner_id=current_user.id)
        result = {**result, "runtime": {"url": observed["url"], "title": observed["title"]}}
    return result


@router.post("/browser/observe")
async def observe_application_browser(req: CaseIdRequest, current_user: CurrentUser = Depends(require_permission("application.browser.connect"))):
    service._require_case(current_user, req.case_id)
    return await runtime.observe(req.case_id)


@router.post("/browser/action")
async def act_application_browser(req: BrowserActionRequest, current_user: CurrentUser = Depends(require_permission("application.case.edit_self"))):
    service._require_case(current_user, req.case_id)
    return await runtime.act(req.case_id, req.action, req.target, req.value)


@router.websocket("/browser/live/{case_id}")
async def live_application_browser(websocket: WebSocket, case_id: str):
    """Authenticated live stream for a Playwright case; actions are JSON messages."""
    try:
        user = get_current_user_from_token(f"Bearer {websocket.query_params.get('token', '')}")
        if "application.browser.connect" not in user.permissions:
            await websocket.close(code=4403); return
        service._require_case(user, case_id)
    except (AuthError, HTTPException):
        await websocket.close(code=4401); return
    await websocket.accept()
    try:
        while True:
            observed = await runtime.observe(case_id)
            await websocket.send_json(observed)
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=0.8)
                if message.get("action"):
                    observed = await runtime.act(case_id, message["action"], message.get("target", ""), message.get("value"))
                    await websocket.send_json(observed)
            except asyncio.TimeoutError:
                continue
    except (WebSocketDisconnect, RuntimeError):
        return


@router.post("/sync/plan")
def sync_application_draft(req: SyncRequest, current_user: CurrentUser = Depends(require_permission("application.case.edit_self"))):
    return service.sync_draft(current_user, req.case_id, req.approved)


@router.post("/cases/submit")
def submit_application(req: SubmitRequest, current_user: CurrentUser = Depends(require_permission("application.case.edit_self"))):
    return service.submit_application(current_user, req.case_id)


@router.post("/workflows/definitions/list")
def list_workflow_definitions(current_user: CurrentUser = Depends(require_permission("application.case.read_self"))):
    return workflow_service.list_definitions()


@router.post("/workflows/instances/start")
def start_workflow(req: CaseCreateRequest, current_user: CurrentUser = Depends(require_permission("application.case.create"))):
    return workflow_service.start_workflow(current_user, req.business_code)


@router.post("/workflows/instances/list")
def list_workflow_instances(current_user: CurrentUser = Depends(require_permission("application.case.read_self"))):
    return workflow_service.list_instances(current_user)


@router.post("/workflows/instances/action")
def workflow_action(req: WorkflowActionRequest, current_user: CurrentUser = Depends(require_permission("application.case.edit_self"))):
    return workflow_service.act(current_user, req.case_id, req.action, req.comment)
