from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CaseCreateRequest(BaseModel):
    business_code: str


class CaseIdRequest(BaseModel):
    case_id: str


class DraftFieldUpdateRequest(CaseIdRequest):
    field_key: str
    value: Any
    expected_revision: int | None = Field(default=None, ge=0)


class BrowserConnectRequest(CaseIdRequest):
    device_name: str = Field(default="本机演示浏览器", max_length=100)


class SyncRequest(CaseIdRequest):
    approved: bool = False


class SubmitRequest(CaseIdRequest):
    pass


class WorkflowActionRequest(BaseModel):
    case_id: str
    action: str
    comment: str | None = None


class ApplicationCase(BaseModel):
    id: str
    business_code: str
    definition_version: str
    status: str
    current_step: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApplicationDetail(ApplicationCase):
    definition: dict[str, Any]
    fields: list[dict[str, Any]]
    materials: list[dict[str, Any]]
    browser: dict[str, Any] | None = None
    next_action: dict[str, Any] | None = None
