from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


InsuranceType = Literal["PENSION", "MEDICAL", "UNEMPLOYMENT", "WORK_INJURY", "MATERNITY"]


class SocialSecuritySummary(BaseModel):
    insured_status: str
    insured_unit: str | None = None
    first_insured_date: date | None = None
    current_base: float = 0
    total_payment_months: int = 0
    pension_account_balance: float = 0
    medical_account_balance: float = 0
    updated_at: datetime | None = None


class SocialSecurityPaymentRecord(BaseModel):
    payment_month: str
    insurance_type: str
    payment_base: float
    personal_amount: float
    company_amount: float
    total_amount: float
    paid_status: str
    paid_at: date | None = None


class SocialSecuritySearchToolInput(BaseModel):
    query_type: Literal["summary", "payments", "accounts"] = Field(
        default="summary",
        description="查询类型：summary=参保概要，payments=缴费记录，accounts=账户余额",
    )
    insurance_type: InsuranceType | None = Field(
        default=None,
        description="可选险种过滤：PENSION=养老，MEDICAL=医疗，UNEMPLOYMENT=失业，WORK_INJURY=工伤，MATERNITY=生育",
    )
    start_month: str | None = Field(default=None, description="可选起始缴费月份，格式 YYYY-MM")
    end_month: str | None = Field(default=None, description="可选结束缴费月份，格式 YYYY-MM")
    limit: int = Field(default=12, ge=1, le=36, description="最多返回的缴费记录条数，1到36之间")
