"""Deterministic approval state machine for the demo business-process center."""

from quest_rag.applications import store
from quest_rag.applications.definitions import get_definition
from quest_rag.applications.service import create_application, get_application_detail
from quest_rag.applications.workflow_definitions import get_workflow_definition, list_workflow_definitions
from quest_rag.auth.schemas import CurrentUser


def list_definitions() -> list[dict]:
    return list_workflow_definitions()


def start_workflow(user: CurrentUser, business_code: str) -> dict:
    workflow = get_workflow_definition(business_code)
    detail = create_application(user, workflow["form_business_code"])
    store.create_workflow_task(detail["id"], "APPLICANT", "USER")
    store.log_action(detail["id"], user.id, "WORKFLOW_STARTED", {"workflow": business_code})
    return get_workflow_detail(user, detail["id"])


def get_workflow_detail(user: CurrentUser, case_id: str) -> dict:
    detail = get_application_detail(user, case_id)
    workflow = get_workflow_definition(detail["business_code"])
    detail["workflow"] = workflow
    detail["tasks"] = store.get_workflow_tasks(case_id)
    detail["pending_task"] = store.get_pending_workflow_task(case_id)
    return detail


def list_instances(user: CurrentUser) -> list[dict]:
    # The existing application list is the canonical case list for the demo.
    from quest_rag.applications import service
    return [get_workflow_detail(user, item["id"]) for item in service.list_application_cases(user)]


def act(user: CurrentUser, case_id: str, action: str, comment: str | None = None) -> dict:
    detail = get_workflow_detail(user, case_id)
    pending = detail.get("pending_task")
    if not pending:
        raise ValueError("当前申请没有待处理审批任务")
    node = pending["node_code"]
    if node == "APPLICANT" and action != "submit":
        raise ValueError("申请人阶段只能提交")
    if node != "APPLICANT" and user.role not in {"ADMIN", "OPERATOR"}:
        raise PermissionError("当前账号不是审批人员")
    if action not in {"submit", "approve", "return"}:
        raise ValueError("不支持的流程动作")

    store.complete_workflow_task(pending["id"], "COMPLETED" if action != "return" else "RETURNED", user.id, comment)
    if action == "return":
        store.update_case(case_id, "RETURNED", "APPLICANT")
        store.create_workflow_task(case_id, "APPLICANT", "USER")
    elif action == "submit":
        store.update_case(case_id, "PENDING_APPROVAL", "HR_REVIEW")
        store.create_workflow_task(case_id, "HR_REVIEW", "OPERATOR")
    elif node == "HR_REVIEW":
        store.update_case(case_id, "PENDING_APPROVAL", "MANAGER_REVIEW")
        store.create_workflow_task(case_id, "MANAGER_REVIEW", "OPERATOR")
    else:
        store.update_case(case_id, "COMPLETED", "COMPLETED")
    store.log_action(case_id, user.id, f"WORKFLOW_{action.upper()}", {"comment": comment or ""})
    return get_workflow_detail(user, case_id)
