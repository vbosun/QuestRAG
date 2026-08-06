from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from quest_rag.auth.dependencies import require_permission, require_rag_scope
from quest_rag.auth.schemas import CurrentUser
from quest_rag.social_security.schemas import SocialSecurityPaymentRecord, SocialSecuritySummary
from quest_rag.social_security.service import get_my_social_security_summary, list_my_payment_records

router = APIRouter(prefix="/public-services", tags=["PUBLIC_SERVICES"])


class SocialSecurityPaymentsRequest(BaseModel):
    insurance_type: str | None = None
    start_month: str | None = None
    end_month: str | None = None
    limit: int = Field(default=24, ge=1, le=36)


@router.post("/social-security/summary", response_model=SocialSecuritySummary)
def social_security_summary(
    current_user: CurrentUser = Depends(require_permission("public_services.social_security.view")),
    _: CurrentUser = Depends(require_rag_scope("social_security_mock")),
):
    return get_my_social_security_summary(current_user)


@router.post("/social-security/payments", response_model=list[SocialSecurityPaymentRecord])
def social_security_payments(
    req: SocialSecurityPaymentsRequest,
    current_user: CurrentUser = Depends(require_permission("public_services.social_security.view")),
    _: CurrentUser = Depends(require_rag_scope("social_security_mock")),
):
    return list_my_payment_records(
        current_user,
        insurance_type=req.insurance_type,
        start_month=req.start_month,
        end_month=req.end_month,
        limit=req.limit,
    )
