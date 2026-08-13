from datetime import datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from quest_rag.applications import service
from quest_rag.auth.schemas import CurrentUser
from quest_rag.rag import tools as rag_tools
from quest_rag.chat_memory.artifacts import parse_message_parts


def test_agent_date_input_is_normalized_for_browser_form():
    assert rag_tools._normalize_form_date("2026年8月13日") == "2026-08-13"
    assert rag_tools._normalize_form_date("2026/08/13") == "2026-08-13"


def make_user() -> CurrentUser:
    return CurrentUser(
        id=7, sid="application-test", role="USER", roles=["USER"], status=1, token_version=1,
        full_name="测试用户", phone="13800138000", permissions=[], rag_scopes=[],
    )


@pytest.fixture
def application_store(monkeypatch):
    state = {"case": None, "fields": {}, "attachments": {}, "browser": None, "logs": []}

    def create_case(user_id, business_code, version, status, step):
        state["case"] = {
            "id": "case-1", "user_id": user_id, "business_code": business_code,
            "definition_version": version, "status": status, "current_step": step,
            "created_at": datetime.now(), "updated_at": datetime.now(),
        }
        return state["case"]

    def get_case(user_id, case_id):
        return state["case"] if state["case"] and state["case"]["id"] == case_id and state["case"]["user_id"] == user_id else None

    def get_fields(case_id):
        return list(state["fields"].values())

    def get_field(case_id, field_key):
        return state["fields"].get(field_key)

    def upsert_field(case_id, field_key, value, source, sync_state, revision):
        row = {"case_id": case_id, "field_key": field_key, "value": value, "source": source, "sync_state": sync_state, "revision": revision}
        state["fields"][field_key] = row
        return row

    def get_attachments(case_id):
        return list(state["attachments"].values())

    def add_attachment(case_id, material_key, original_name, content_type, content):
        row = {"id": "attachment-1", "material_key": material_key, "original_name": original_name, "content_type": content_type, "size_bytes": len(content)}
        state["attachments"][material_key] = row
        return row

    def upsert_browser_connection(case_id, user_id, device_name, adapter_id, entry_url):
        state["browser"] = {"case_id": case_id, "user_id": user_id, "device_name": device_name, "status": "connected", "adapter_id": adapter_id, "entry_url": entry_url, "last_page": "application_form", "last_error": None}
        return state["browser"]

    def update_case(case_id, status, current_step):
        state["case"].update(status=status, current_step=current_step)
        return state["case"]

    monkeypatch.setattr(service.store, "create_case", create_case)
    monkeypatch.setattr(service.store, "get_case", get_case)
    monkeypatch.setattr(service.store, "get_fields", get_fields)
    monkeypatch.setattr(service.store, "get_field", get_field)
    monkeypatch.setattr(service.store, "upsert_field", upsert_field)
    monkeypatch.setattr(service.store, "get_attachments", get_attachments)
    monkeypatch.setattr(service.store, "add_attachment", add_attachment)
    monkeypatch.setattr(service.store, "get_browser_connection", lambda case_id: state["browser"])
    monkeypatch.setattr(service.store, "upsert_browser_connection", upsert_browser_connection)
    monkeypatch.setattr(service.store, "update_case", update_case)
    monkeypatch.setattr(service.store, "log_action", lambda *args, **kwargs: state["logs"].append((args, kwargs)))
    return state


def test_user_changes_are_versioned_and_readonly_profile_cannot_change(application_store):
    user = make_user()
    detail = service.create_application(user, "employment_registration")
    assert detail["fields"][0]["value"] == "测试用户"
    assert next(field for field in detail["fields"] if field["key"] == "phone")["value"] == "13800138000"

    with pytest.raises(HTTPException) as error:
        service.update_draft_field(user, "case-1", "full_name", "其他姓名")
    assert error.value.status_code == 403

    changed = service.update_draft_field(user, "case-1", "phone", "13800138000", 1)
    assert changed == {"field_key": "phone", "value": "13800138000", "source": "user_manual", "revision": 2, "sync_state": "pending"}


def test_confirmed_conversation_values_are_prefilled(application_store):
    detail = service.create_application(
        make_user(), "employment_registration",
        {"phone": "18733333333", "employment_type": "employer"},
    )
    values = {field["key"]: field["value"] for field in detail["fields"]}
    assert values["phone"] == "18733333333"
    assert values["employment_type"] == "employer"


def test_registration_sync_never_submits(application_store):
    user = make_user()
    service.create_application(user, "employment_registration")
    service.update_draft_field(user, "case-1", "phone", "13800138000")
    service.update_draft_field(user, "case-1", "employment_type", "employer")
    service.update_draft_field(user, "case-1", "employer_name", "测试单位")
    service.update_draft_field(user, "case-1", "occupation", "行政文员")
    service.update_draft_field(user, "case-1", "employment_start_date", "2026-01-01")
    service.update_draft_field(user, "case-1", "current_address", "测试市测试区")
    service.upload_material(user, "case-1", "employment_proof", "contract.pdf", "application/pdf", b"test")
    service.connect_browser(user, "case-1", "test-browser")

    pending = service.sync_draft(user, "case-1", False)
    assert pending["requires_approval"] is False
    assert application_store["case"]["status"] == "REVIEW"
    assert pending["message"]
    assert all(field["sync_state"] == "synced" for field in application_store["fields"].values())


def test_agent_start_returns_renderable_application_artifact(application_store, monkeypatch):
    user = make_user()
    monkeypatch.setattr(rag_tools, "assert_tool_permission", lambda *args: None)
    token = rag_tools.current_user_ctx.set(user)
    try:
        output = rag_tools.start_application.invoke({"business_code": "employment_registration"})
    finally:
        rag_tools.current_user_ctx.reset(token)
    assert "```questrag-artifact" in output
    assert '"type": "application"' in output
    assert '"case_id": "case-1"' in output
    parts = parse_message_parts(output)
    assert next(part for part in parts if part["type"] == "application")["artifact"]["case_id"] == "case-1"


def test_agent_start_normalizes_postgres_uuid_in_artifact(monkeypatch):
    user = make_user()
    case_id = uuid4()
    monkeypatch.setattr(rag_tools, "assert_tool_permission", lambda *args: None)
    monkeypatch.setattr(
        rag_tools,
        "create_application",
        lambda *_args: {"id": case_id, "definition": {"name": "就业登记申请"}},
    )
    token = rag_tools.current_user_ctx.set(user)
    try:
        output = rag_tools.start_application.invoke({"business_code": "employment_registration"})
    finally:
        rag_tools.current_user_ctx.reset(token)
    parts = parse_message_parts(output)
    artifact = next(part for part in parts if part["type"] == "application")["artifact"]
    assert artifact["case_id"] == str(case_id)
    assert artifact["id"] == f"application_{case_id}"


def test_registration_guidance_and_eligibility_are_structured_for_agent():
    user = make_user()
    guidance = service.get_application_guidance("employment_registration")
    assert guidance["name"] == "就业登记申请"
    assert guidance["materials"][0]["key"] == "employment_proof"

    waiting = service.assess_application_eligibility(user, "employment_registration")
    assert waiting["status"] == "needs_information"
    assert "是否已经开始就业、灵活就业或自主创业" in waiting["missing"]

    rejected = service.assess_application_eligibility(user, "employment_registration", False)
    assert rejected["status"] == "not_eligible"

    eligible = service.assess_application_eligibility(user, "employment_registration", True)
    assert eligible["status"] == "eligible"


def test_unemployment_registration_eligibility_uses_unemployed_condition():
    user = make_user()
    eligible = service.assess_application_eligibility(user, "unemployment_registration", is_unemployed=True)
    assert eligible["status"] == "eligible"
    rejected = service.assess_application_eligibility(user, "unemployment_registration", is_unemployed=False)
    assert rejected["status"] == "not_eligible"
