"""Small, JSON-friendly workflow catalog used by the application test center.

The catalog deliberately models a human approval state machine instead of
embedding approval rules in the Agent prompt.  New demo business processes can
be added here (or loaded from a later admin editor) without changing Agent code.
"""

from copy import deepcopy


WORKFLOW_DEFINITIONS: dict[str, dict] = {
    "employment_registration": {
        "business_code": "employment_registration",
        "name": "就业登记申请审批",
        "version": "2026.08.mock.1",
        "form_business_code": "employment_registration",
        "nodes": [
            {"code": "APPLICANT", "name": "申请人提交", "kind": "applicant", "role": "USER"},
            {"code": "HR_REVIEW", "name": "人社经办初审", "kind": "approval", "role": "OPERATOR"},
            {"code": "MANAGER_REVIEW", "name": "业务负责人复审", "kind": "approval", "role": "OPERATOR"},
            {"code": "COMPLETED", "name": "办理完成", "kind": "terminal", "role": None},
        ],
        "transitions": {
            "APPLICANT": ["submit"],
            "HR_REVIEW": ["approve", "return"],
            "MANAGER_REVIEW": ["approve", "return"],
            "COMPLETED": [],
        },
    }
}


def list_workflow_definitions() -> list[dict]:
    return [deepcopy(item) for item in WORKFLOW_DEFINITIONS.values()]


def get_workflow_definition(business_code: str) -> dict:
    try:
        return deepcopy(WORKFLOW_DEFINITIONS[business_code])
    except KeyError as exc:
        raise ValueError(f"未登记的业务流程: {business_code}") from exc
