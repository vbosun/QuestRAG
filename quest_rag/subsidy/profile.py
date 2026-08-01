import re
from datetime import date
from typing import Any

from quest_rag.auth.schemas import CurrentUser
from quest_rag.social_security.store import get_profile, list_payment_records
from quest_rag.subsidy.schemas import SubsidyUserProfile


def build_subsidy_profile(
    current_user: CurrentUser,
    user_description: str = "",
    extracted_facts: dict | None = None,
) -> SubsidyUserProfile:
    facts = _extract_facts_from_text(user_description)
    facts.update(extracted_facts or {})
    social = get_profile(current_user.id) or {}
    payment_records = list_payment_records(current_user.id, limit=72)
    actual_payment = sum(float(item["personal_amount"] or 0) for item in payment_records)

    person_tags = set(_as_list(facts.get("person_tags")))
    if facts.get("is_college_graduate") is True:
        person_tags.add("college_graduate")
    graduation_year = _to_int(facts.get("graduation_year"))
    if graduation_year and date.today().year - graduation_year <= 2:
        person_tags.add("college_graduate_within_2_years")
    if facts.get("employment_difficulty_person") is True:
        person_tags.add("employment_difficulty_person")
    if "就业困难" in user_description:
        person_tags.add("employment_difficulty_person")
    if "返乡" in user_description:
        person_tags.add("returning_entrepreneur")
    if "退役" in user_description:
        person_tags.add("veteran")

    return SubsidyUserProfile(
        user_id=current_user.id,
        region=facts.get("region") or "甘肃省",
        person_tags=sorted(person_tags),
        employment_status=facts.get("employment_status"),
        graduation_year=graduation_year,
        is_college_graduate=facts.get("is_college_graduate"),
        business_status=facts.get("business_status"),
        business_months=_to_int(facts.get("business_months")),
        first_business=facts.get("first_business"),
        social_insurance_status=social.get("insured_status"),
        social_insurance_months=social.get("total_payment_months"),
        current_payment_base=float(social.get("current_base") or 0) if social else None,
        actual_social_insurance_payment=round(actual_payment, 2) if actual_payment else None,
    )


def _extract_facts_from_text(text: str) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    if any(word in text for word in ["高校", "大学", "毕业生", "毕业"]):
        facts["is_college_graduate"] = True
    match = re.search(r"(20\d{2})\s*年?\s*毕业", text)
    if match:
        facts["graduation_year"] = int(match.group(1))
    if any(word in text for word in ["灵活就业", "自己交社保", "个人交社保"]):
        facts["employment_status"] = "flexible_employment"
    if any(word in text for word in ["开店", "创业", "营业执照", "个体经营"]):
        facts["business_status"] = "active"
    if any(word in text for word in ["首次创业", "第一次创业", "第一次开店"]):
        facts["first_business"] = True
    month_match = re.search(r"(运营|经营).{0,4}(\d+)\s*个?月", text)
    if month_match:
        facts["business_months"] = int(month_match.group(2))
    year_match = re.search(r"(运营|经营).{0,4}(\d+)\s*年", text)
    if year_match:
        facts["business_months"] = int(year_match.group(2)) * 12
    return facts


def merge_profile_with_inputs(profile: SubsidyUserProfile, user_inputs: dict) -> SubsidyUserProfile:
    data = profile.model_dump()
    for key, value in user_inputs.items():
        if value is not None and value != "":
            data[key] = value
    if data.get("is_college_graduate") and data.get("graduation_year") and date.today().year - int(data["graduation_year"]) <= 2:
        tags = set(data.get("person_tags") or [])
        tags.add("college_graduate_within_2_years")
        data["person_tags"] = sorted(tags)
    return SubsidyUserProfile(**data)


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _to_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
