import hashlib
from datetime import date
from typing import Any
from urllib.parse import urlencode

from fastapi import HTTPException

from quest_rag.applications import definitions, store
from quest_rag.auth.schemas import CurrentUser


USER_MANUAL = "user_manual"
PROFILE_PREFILL = "profile_prefill"


def create_application(user: CurrentUser, business_code: str, conversation_prefill: dict | None = None) -> dict:
    definition = definitions.get_definition(business_code)
    if not definition:
        raise HTTPException(status_code=404, detail={"code": "BUSINESS_NOT_FOUND", "message": "未找到可办理业务"})
    first_step = definition["steps"][0]
    case = store.create_case(user.id, business_code, definition["version"], first_step["state"], first_step["code"])
    profile_values = {"full_name": user.full_name, "phone": user.phone}
    conversation_prefill = conversation_prefill or {}
    for field in definition["form"]["fields"]:
        value = conversation_prefill.get(field["key"]) or profile_values.get(field["key"])
        if value:
            source = "conversation_confirmed" if field["key"] in conversation_prefill else PROFILE_PREFILL
            store.upsert_field(case["id"], field["key"], value, source, "pending", 1)
    store.log_action(case["id"], user.id, "CASE_CREATED", {"business_code": business_code, "definition_version": definition["version"]})
    return get_application_detail(user, case["id"])


def list_application_cases(user: CurrentUser) -> list[dict]:
    return [
        {
            "id": item["id"], "business_code": item["business_code"],
            "definition_version": item["definition_version"], "status": item["status"],
            "current_step": item["current_step"], "created_at": item.get("created_at"), "updated_at": item.get("updated_at"),
        }
        for item in store.list_cases(user.id)
    ]


def list_available_applications() -> list[dict]:
    """Return registered services that the Agent may introduce or start."""
    return definitions.list_definitions()


def get_application_guidance(business_code: str) -> dict:
    definition = definitions.get_definition(business_code)
    if not definition:
        raise HTTPException(status_code=404, detail={"code": "BUSINESS_NOT_FOUND", "message": "未找到可办理业务"})
    return {
        "business_code": definition["business_code"], "name": definition["name"], "region": definition.get("region"),
        "eligibility": definition.get("eligibility", {}), "steps": definition["steps"],
        "fields": [{key: field.get(key) for key in ("key", "label", "required", "type", "editable")} for field in definition["form"]["fields"]],
        "materials": definition["form"].get("materials", []),
    }


def assess_application_eligibility(
    user: CurrentUser,
    business_code: str,
    has_started_employment: bool | None = None,
    phone: str | None = None,
    is_unemployed: bool | None = None,
) -> dict:
    definition = definitions.get_definition(business_code)
    if not definition:
        raise HTTPException(status_code=404, detail={"code": "BUSINESS_NOT_FOUND", "message": "未找到可办理业务"})
    missing = []
    if not user.full_name:
        missing.append("姓名")
    if not (phone or user.phone):
        missing.append("联系电话")
    if business_code == "unemployment_registration":
        if is_unemployed is None:
            missing.append("当前是否处于失业状态")
    elif has_started_employment is None:
        missing.append("是否已经开始就业、灵活就业或自主创业")
    if missing:
        return {"business_code": business_code, "status": "needs_information", "missing": missing, "message": f"暂不能判断是否可发起申请，请补充：{'、'.join(missing)}。"}
    if business_code == "unemployment_registration":
        if not is_unemployed:
            return {"business_code": business_code, "status": "not_eligible", "missing": [], "message": "失业登记适用于当前处于失业状态的情形；当前不满足模拟申请条件。"}
        return {"business_code": business_code, "status": "eligible", "missing": [], "message": "基础条件已满足，可以发起失业登记申请；后续仍需以官方审核结果为准。"}
    if not has_started_employment:
        return {"business_code": business_code, "status": "not_eligible", "missing": [], "message": "就业登记用于已开始单位就业、灵活就业或自主创业的情形；当前不满足模拟申请条件。"}
    return {"business_code": business_code, "status": "eligible", "missing": [], "message": "基础条件已满足，可以发起就业登记申请；后续仍需以官方审核结果为准。"}


def get_application_detail(user: CurrentUser, case_id: str) -> dict:
    case = _require_case(user, case_id)
    definition = definitions.get_definition(case["business_code"])
    if not definition or definition["version"] != case["definition_version"]:
        raise HTTPException(status_code=409, detail={"code": "DEFINITION_UNAVAILABLE", "message": "该申请使用的流程版本不可用"})
    values = {row["field_key"]: row for row in store.get_fields(case_id)}
    fields = []
    for field in definition["form"]["fields"]:
        persisted = values.get(field["key"])
        fields.append({
            **field,
            "value": persisted["value"] if persisted else None,
            "source": persisted["source"] if persisted else field.get("source"),
            "revision": persisted["revision"] if persisted else 0,
            "sync_state": persisted["sync_state"] if persisted else "pending",
        })
    attachments = {item["material_key"]: item for item in store.get_attachments(case_id)}
    materials = [
        {**item, "status": "uploaded" if item["key"] in attachments else ("required" if item["required"] else "optional"), "attachment": attachments.get(item["key"])}
        for item in definition["form"].get("materials", [])
    ]
    material_complete = all(not material["required"] or material["status"] == "uploaded" for material in materials)
    browser = store.get_browser_connection(case_id)
    return {
        **case, "definition": _public_definition(definition), "fields": fields,
        "materials": materials,
        "browser": browser, "next_action": _next_action(case, browser, fields, material_complete),
    }


def update_draft_field(user: CurrentUser, case_id: str, field_key: str, value: Any, expected_revision: int | None = None) -> dict:
    case = _require_case(user, case_id)
    definition = definitions.get_definition(case["business_code"])
    field = next((item for item in definition["form"]["fields"] if item["key"] == field_key), None)
    if not field:
        raise HTTPException(status_code=404, detail={"code": "FIELD_NOT_FOUND", "message": "字段不属于当前申请"})
    if not field.get("editable", True):
        raise HTTPException(status_code=403, detail={"code": "FIELD_READ_ONLY", "message": "该字段由官方或个人档案维护，不能在申请中修改"})
    _validate_field(field, value)
    existing = store.get_field(case_id, field_key)
    current_revision = int(existing["revision"]) if existing else 0
    if expected_revision is not None and expected_revision != current_revision:
        raise HTTPException(status_code=409, detail={"code": "STALE_DRAFT", "message": "表单已更新，请刷新后再修改"})
    row = store.upsert_field(case_id, field_key, value, USER_MANUAL, "pending", current_revision + 1)
    store.log_action(case_id, user.id, "FIELD_UPDATED", {"field_key": field_key, "source": USER_MANUAL, "revision": row["revision"]})
    return {"field_key": row["field_key"], "value": row["value"], "source": row["source"], "revision": row["revision"], "sync_state": row["sync_state"]}


def connect_browser(user: CurrentUser, case_id: str, device_name: str) -> dict:
    case = _require_case(user, case_id)
    definition = definitions.get_definition(case["business_code"])
    adapter = definition["adapter"]
    values = {field["key"]: field["value"] for field in get_application_detail(user, case_id)["fields"] if field.get("value") is not None}
    prefill = {key: values[key] for key in ("full_name", "phone", "employment_type") if values.get(key)}
    query = f"?{urlencode(prefill)}" if prefill else ""
    entry_url = f"{adapter['allowed_origins'][0]}{adapter['entry_path']}{query}"
    browser = store.upsert_browser_connection(case_id, user.id, device_name, definition["adapter_id"], entry_url)
    store.log_action(case_id, user.id, "BROWSER_CONNECTED", {"adapter_id": definition["adapter_id"], "entry_url": entry_url})
    return _browser_public(browser)


def upload_material(user: CurrentUser, case_id: str, material_key: str, original_name: str, content_type: str | None, content: bytes) -> dict:
    case = _require_case(user, case_id)
    definition = definitions.get_definition(case["business_code"])
    material = next((item for item in definition["form"].get("materials", []) if item["key"] == material_key), None)
    if not material:
        raise HTTPException(status_code=404, detail={"code": "MATERIAL_NOT_FOUND", "message": "该材料不属于当前申请"})
    if not content:
        raise HTTPException(status_code=422, detail={"code": "EMPTY_ATTACHMENT", "message": "不能上传空文件"})
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=422, detail={"code": "ATTACHMENT_TOO_LARGE", "message": "单个材料不能超过 10MB"})
    row = store.add_attachment(case_id, material_key, original_name or "未命名材料", content_type, content)
    store.log_action(case_id, user.id, "MATERIAL_UPLOADED", {"material_key": material_key, "size_bytes": row["size_bytes"]})
    return row


def sync_draft(user: CurrentUser, case_id: str, approved: bool) -> dict:
    case = _require_case(user, case_id)
    browser = store.get_browser_connection(case_id)
    if not browser or browser["status"] != "connected":
        raise HTTPException(status_code=409, detail={"code": "BROWSER_NOT_CONNECTED", "message": "请先连接本机浏览器"})
    detail = get_application_detail(user, case_id)
    missing_required = [field["label"] for field in detail["fields"] if field.get("required") and field.get("value") in (None, "")]
    if missing_required:
        raise HTTPException(status_code=422, detail={"code": "MISSING_REQUIRED_FIELDS", "message": f"请先补充：{'、'.join(missing_required)}"})
    missing_materials = [material["label"] for material in detail["materials"] if material.get("required") and material["status"] != "uploaded"]
    if missing_materials:
        raise HTTPException(status_code=422, detail={"code": "MISSING_REQUIRED_MATERIALS", "message": f"请先上传：{'、'.join(missing_materials)}"})
    pending = [field for field in detail["fields"] if field["value"] is not None and field["sync_state"] != "synced"]
    sensitive = [field["label"] for field in pending if field.get("sensitive")]
    if sensitive and not approved:
        return {"requires_approval": True, "sensitive_fields": sensitive, "message": "包含敏感字段，确认后才会同步到官方表单。"}
    synced = []
    for field in pending:
        value_hash = hashlib.sha256(str(field["value"]).encode("utf-8")).hexdigest()
        row = store.upsert_field(case_id, field["key"], field["value"], field["source"] or USER_MANUAL, "synced", int(field["revision"]))
        synced.append({"field_key": row["field_key"], "value_hash": value_hash})
    store.update_case(case_id, "REVIEW", "review")
    store.log_action(case_id, user.id, "DRAFT_SYNCED", {"field_count": len(synced), "approved_sensitive": approved})
    return {"requires_approval": False, "synced": synced, "message": "已同步到受控演示官方表单，等待用户在官方页面完成承诺与提交。"}


def submit_application(user: CurrentUser, case_id: str) -> dict:
    """Record an explicit user click as a mock submission; never calls an official service."""
    detail = get_application_detail(user, case_id)
    missing = [field["label"] for field in detail["fields"] if field.get("required") and field.get("value") in (None, "")]
    missing.extend(material["label"] for material in detail["materials"] if material["required"] and material["status"] != "uploaded")
    if missing:
        raise HTTPException(status_code=422, detail={"code": "INCOMPLETE_APPLICATION", "message": f"请先补充：{'、'.join(missing)}"})
    updated = store.update_case(case_id, "SUBMITTED", "user_confirmation")
    store.log_action(case_id, user.id, "USER_SUBMITTED_DEMO", {"official_submission": False})
    return {"status": updated["status"], "current_step": updated["current_step"], "message": "已记录您的提交操作（演示流程），不会向真实官方系统提交。"}


def agent_application_summary(user: CurrentUser, case_id: str) -> str:
    detail = get_application_detail(user, case_id)
    return f"申请 {detail['definition']['name']} 当前处于 {detail['current_step']}；{detail['next_action']['message']}"


def _require_case(user: CurrentUser, case_id: str) -> dict:
    case = store.get_case(user.id, case_id)
    if not case:
        raise HTTPException(status_code=404, detail={"code": "CASE_NOT_FOUND", "message": "申请不存在或不属于当前用户"})
    return case


def _public_definition(definition: dict) -> dict:
    return {key: definition[key] for key in ("business_code", "version", "name", "region", "official_service_name", "steps")}


def _browser_public(browser: dict | None) -> dict | None:
    if not browser:
        return None
    return {key: browser.get(key) for key in ("device_name", "status", "adapter_id", "entry_url", "last_page", "last_error", "updated_at")}


def _next_action(case: dict, browser: dict | None, fields: list[dict], material_complete: bool) -> dict:
    missing = [field["label"] for field in fields if field.get("required") and field.get("value") in (None, "")]
    if missing:
        return {"code": "FILL_FIELDS", "message": f"请补充：{'、'.join(missing)}"}
    if not material_complete:
        return {"code": "UPLOAD_MATERIALS", "message": "请上传必需申请材料"}
    if not browser:
        return {"code": "CONNECT_BROWSER", "message": "资料已齐全，可以由 Agent 打开已登记的官方申请入口"}
    if any(field["sync_state"] != "synced" for field in fields if field.get("value") is not None):
        return {"code": "SYNC_DRAFT", "message": "请确认将草稿同步到官方表单"}
    return {"code": "WAITING_USER", "message": "已同步。验证码、承诺和最终提交必须由您在官方页面完成。"}


def _validate_field(field: dict, value: Any) -> None:
    if field.get("required") and value in (None, ""):
        raise HTTPException(status_code=422, detail={"code": "REQUIRED", "message": f"{field['label']}不能为空"})
    if field.get("type") == "phone" and value and (not isinstance(value, str) or len(value) != 11 or not value.isdigit()):
        raise HTTPException(status_code=422, detail={"code": "INVALID_PHONE", "message": "联系电话应为 11 位数字"})
    if field.get("validator") == "date_not_future" and value:
        try:
            if date.fromisoformat(value) > date.today():
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=422, detail={"code": "INVALID_DATE", "message": "日期不能晚于今天"})
