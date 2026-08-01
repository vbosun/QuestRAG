from fastapi import APIRouter, Depends

from quest_rag.auth.dependencies import require_permission
from quest_rag.auth.schemas import CurrentUser
from quest_rag.social_security.schemas import SocialSecurityPaymentRecord, SocialSecuritySummary
from quest_rag.social_security.service import get_my_social_security_summary, list_my_payment_records

router = APIRouter(prefix="/public-services", tags=["PUBLIC_SERVICES"])


@router.get("/social-security/summary", response_model=SocialSecuritySummary)
def social_security_summary(
    current_user: CurrentUser = Depends(require_permission("public_services.social_security.view")),
):
    return get_my_social_security_summary(current_user)


@router.get("/social-security/payments", response_model=list[SocialSecurityPaymentRecord])
def social_security_payments(
    insurance_type: str | None = None,
    start_month: str | None = None,
    end_month: str | None = None,
    limit: int = 24,
    current_user: CurrentUser = Depends(require_permission("public_services.social_security.view")),
):
    return list_my_payment_records(
        current_user,
        insurance_type=insurance_type,
        start_month=start_month,
        end_month=end_month,
        limit=max(1, min(limit, 36)),
    )
