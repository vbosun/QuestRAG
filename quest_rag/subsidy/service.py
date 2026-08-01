from quest_rag.auth.schemas import CurrentUser
from quest_rag.subsidy.calculator import calculate_subsidy
from quest_rag.subsidy.matcher import match_subsidies
from quest_rag.subsidy.profile import build_subsidy_profile
from quest_rag.subsidy.store import list_calculation_logs, list_policy_rules


def match_for_user(current_user: CurrentUser, user_description: str, extracted_facts: dict | None = None, top_k: int = 5):
    profile = build_subsidy_profile(current_user, user_description, extracted_facts)
    return match_subsidies(profile, user_description, top_k)


def calculate_for_user(current_user: CurrentUser, policy_id: str, user_inputs: dict):
    profile = build_subsidy_profile(current_user, "", user_inputs)
    return calculate_subsidy(policy_id, profile, user_inputs)


def list_policies() -> list[dict]:
    return [
        {
            "id": item["id"],
            "code": item["code"],
            "name": item["name"],
            "category": item["category"],
            "region": item.get("region"),
            "description": item.get("description", ""),
            "source_doc_id": item.get("source_doc_id"),
            "source_title": item.get("source_title"),
        }
        for item in list_policy_rules()
    ]


def calculation_logs_for_user(current_user: CurrentUser, limit: int = 20):
    return list_calculation_logs(current_user.id, limit)
