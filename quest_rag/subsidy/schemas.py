from typing import Any, Literal

from pydantic import BaseModel, Field


class RequiredInput(BaseModel):
    field: str = Field(description="缺失字段的机器字段名，后续补充信息时应使用该字段名")
    label: str = Field(description="缺失字段的中文名称，可用于向用户追问")
    source: str = Field(default="user_input", description="建议的数据来源，例如 user_input/social_security/personal_info")
    required: bool = Field(default=True, description="是否为完成资格判断或测算所必需")


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
    user_description: str = Field(
        min_length=1,
        description=(
            "用户关于补贴资格、补贴金额或个人情况的自然语言描述。"
            "应尽量保留原话，例如“我是2025年毕业的，自己交社保，能领补贴吗”。"
        ),
    )
    extracted_facts: dict = Field(
        default_factory=dict,
        description=(
            "从当前对话中已明确抽取并较可信的结构化事实。"
            "可填写字段包括 is_college_graduate、graduation_year、employment_status、"
            "person_tags、first_business、business_status、business_months。"
            "不要臆测用户未说明的信息。"
        ),
    )
    top_k: int = Field(default=5, ge=1, le=10, description="返回候选补贴数量，默认5，最大10")


class SubsidyCalculateToolInput(BaseModel):
    policy_id: str = Field(
        min_length=1,
        description=(
            "要测算的补贴政策ID，必须来自 subsidy_match 返回的 policy_id，"
            "例如 subsidy_college_graduate_flexible_social_insurance。不要自行编造。"
        ),
    )
    user_inputs: dict = Field(
        default_factory=dict,
        description=(
            "用户已确认或补充的测算字段。字段名应来自 subsidy_match/subsidy_calculate 返回的 missing_inputs.field，"
            "或使用已支持字段：is_college_graduate、graduation_year、employment_status、person_tags、"
            "first_business、business_status、business_months。"
            "布尔值请使用 true/false，年份和月数请使用数字。"
        ),
    )
