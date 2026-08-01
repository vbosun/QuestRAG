from fastapi import APIRouter, Depends

from quest_rag.auth.dependencies import require_permission
from quest_rag.auth.schemas import CurrentUser
from quest_rag.social_security.schemas import SocialSecurityPaymentRecord, SocialSecuritySummary
from quest_rag.social_security.service import get_my_social_security_summary, list_my_payment_records
from quest_rag.subsidy.schemas import (
    SubsidyCalculateRequest,
    SubsidyCalculationResult,
    SubsidyMatchRequest,
    SubsidyMatchResult,
)
from quest_rag.subsidy.service import calculation_logs_for_user, calculate_for_user, list_policies, match_for_user

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


@router.get("/subsidies/policies")
def subsidy_policies(
    current_user: CurrentUser = Depends(require_permission("public_services.subsidy_calculator.view")),
):
    return list_policies()


@router.post("/subsidies/match", response_model=list[SubsidyMatchResult])
def subsidy_match(
    req: SubsidyMatchRequest,
    current_user: CurrentUser = Depends(require_permission("public_services.subsidy_calculator.view")),
):
    return match_for_user(current_user, req.user_description, req.extracted_facts, req.top_k)


@router.post("/subsidies/calculate", response_model=SubsidyCalculationResult)
def subsidy_calculate(
    req: SubsidyCalculateRequest,
    current_user: CurrentUser = Depends(require_permission("public_services.subsidy_calculator.view")),
):
    return calculate_for_user(current_user, req.policy_id, req.user_inputs)


@router.get("/subsidies/calculation-logs")
def subsidy_calculation_logs(
    limit: int = 20,
    current_user: CurrentUser = Depends(require_permission("public_services.subsidy_calculator.view")),
):
    return calculation_logs_for_user(current_user, max(1, min(limit, 50)))
