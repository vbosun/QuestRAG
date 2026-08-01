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
    insurance_type: InsuranceType | None = None
    start_month: str | None = Field(default=None, description="YYYY-MM")
    end_month: str | None = Field(default=None, description="YYYY-MM")
    limit: int = Field(default=12, ge=1, le=36)

