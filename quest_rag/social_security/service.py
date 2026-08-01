from quest_rag.auth.schemas import CurrentUser
from quest_rag.social_security.schemas import SocialSecurityPaymentRecord, SocialSecuritySummary
from quest_rag.social_security.store import get_profile, insert_access_log, list_payment_records


def get_my_social_security_summary(current_user: CurrentUser) -> SocialSecuritySummary:
    row = get_profile(current_user.id)
    insert_access_log(current_user.id, "summary", {})
    if not row:
        return SocialSecuritySummary(insured_status="NONE")
    return SocialSecuritySummary(**row)


def list_my_payment_records(
    current_user: CurrentUser,
    insurance_type: str | None = None,
    start_month: str | None = None,
    end_month: str | None = None,
    limit: int = 24,
) -> list[SocialSecurityPaymentRecord]:
    rows = list_payment_records(
        current_user.id,
        insurance_type=insurance_type,
        start_month=start_month,
        end_month=end_month,
        limit=limit,
    )
    insert_access_log(
        current_user.id,
        "payments",
        {"insurance_type": insurance_type, "start_month": start_month, "end_month": end_month, "limit": limit},
    )
    return [SocialSecurityPaymentRecord(**row) for row in rows]


def format_social_security_result(
    current_user: CurrentUser,
    query_type: str,
    insurance_type: str | None = None,
    start_month: str | None = None,
    end_month: str | None = None,
    limit: int = 12,
) -> str:
    summary = get_my_social_security_summary(current_user)
    if summary.insured_status == "NONE":
        return "查询对象：本人\n未查询到本人模拟社保参保记录。"

    lines = [
        "查询对象：本人",
        f"参保状态：{status_label(summary.insured_status)}",
        f"当前参保单位：{summary.insured_unit or '未登记'}",
        f"当前缴费基数：{summary.current_base:.2f} 元",
        f"累计缴费月数：{summary.total_payment_months} 个月",
        f"养老个人账户余额：{summary.pension_account_balance:.2f} 元",
        f"医保个人账户余额：{summary.medical_account_balance:.2f} 元",
    ]
    if query_type in {"payments", "summary"}:
        records = list_my_payment_records(current_user, insurance_type, start_month, end_month, limit)
        if records:
            lines.append("\n最近缴费记录：")
            for item in records:
                lines.append(
                    f"{item.payment_month} {insurance_label(item.insurance_type)} "
                    f"基数{item.payment_base:.2f} 个人{item.personal_amount:.2f} "
                    f"单位{item.company_amount:.2f} 合计{item.total_amount:.2f}"
                )
    return "\n".join(lines)


def status_label(value: str) -> str:
    return {"ACTIVE": "正常参保", "PAUSED": "暂停参保", "TERMINATED": "终止参保", "NONE": "无记录"}.get(value, value)


def insurance_label(value: str) -> str:
    return {
        "PENSION": "养老",
        "MEDICAL": "医疗",
        "UNEMPLOYMENT": "失业",
        "WORK_INJURY": "工伤",
        "MATERNITY": "生育",
    }.get(value, value)
