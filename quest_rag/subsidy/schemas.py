from typing import Any, Literal

from pydantic import BaseModel, Field


class RequiredInput(BaseModel):
    field: str
    label: str
    source: str = "user_input"
    required: bool = True


class ConditionResult(BaseModel):
    field: str
    label: str
    passed: bool
    actual_value: Any = None
    expected_value: Any = None
    message: str


class SubsidyUserProfile(BaseModel):
    user_id: int
    age: int | None = None
    gender: str | None = None
    region: str | None = "甘肃省"
    person_tags: list[str] = Field(default_factory=list)
    employment_status: str | None = None
    graduation_year: int | None = None
    is_college_graduate: bool | None = None
    business_status: str | None = None
    business_months: int | None = None
    first_business: bool | None = None
    social_insurance_status: str | None = None
    social_insurance_months: int | None = None
    current_payment_base: float | None = None
    actual_social_insurance_payment: float | None = None


class SubsidyMatchResult(BaseModel):
    policy_id: str
    policy_name: str
    category: str
    match_status: Literal["eligible", "possible", "not_eligible"]
    match_score: float
    passed_conditions: list[ConditionResult] = Field(default_factory=list)
    failed_conditions: list[ConditionResult] = Field(default_factory=list)
    missing_inputs: list[RequiredInput] = Field(default_factory=list)
    source_doc_id: str | None = None


class SubsidyCalculationResult(BaseModel):
    policy_id: str
    policy_name: str
    eligible: bool
    status: Literal["eligible", "missing_info", "not_eligible"]
    estimated_amount: float | None = None
    amount_range: tuple[float, float] | None = None
    amount_unit: str = "元"
    condition_results: list[ConditionResult] = Field(default_factory=list)
    missing_inputs: list[RequiredInput] = Field(default_factory=list)
    calculation_steps: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    process_steps: list[str] = Field(default_factory=list)
    source_doc_id: str | None = None
    disclaimer: str = "测算结果仅供参考，最终享受政策和发放金额以当地人社部门审核结果为准。"


class SubsidyMatchToolInput(BaseModel):
    user_description: str = Field(description="用户描述的个人情况或咨询问题")
    extracted_facts: dict = Field(default_factory=dict, description="模型从对话中抽取的已知条件")
    top_k: int = Field(default=5, ge=1, le=10)


class SubsidyCalculateToolInput(BaseModel):
    policy_id: str
    user_inputs: dict = Field(default_factory=dict)


class SubsidyMatchRequest(BaseModel):
    user_description: str
    extracted_facts: dict = Field(default_factory=dict)
    top_k: int = Field(default=5, ge=1, le=10)


class SubsidyCalculateRequest(BaseModel):
    policy_id: str
    user_inputs: dict = Field(default_factory=dict)

