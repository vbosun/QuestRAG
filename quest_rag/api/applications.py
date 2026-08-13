from fastapi import APIRouter, Depends, File, Form, UploadFile

from quest_rag.applications import definitions, service
from quest_rag.applications.schemas import BrowserActionRequest, BrowserConnectRequest, CaseCreateRequest, CaseIdRequest, DraftFieldUpdateRequest, SyncRequest, SubmitRequest, WorkflowActionRequest
from quest_rag.applications.playwright_runtime import runtime
from quest_rag.applications import workflow_service
from quest_rag.auth.dependencies import require_permission
from quest_rag.auth.schemas import CurrentUser

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
        observed = await runtime.start(req.case_id, result["entry_url"], values)
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
