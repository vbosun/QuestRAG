from typing import Any

from quest_rag.subsidy.schemas import ConditionResult, RequiredInput, SubsidyMatchResult, SubsidyUserProfile
from quest_rag.subsidy.store import list_policy_rules


def match_subsidies(
    profile: SubsidyUserProfile,
    question: str | None = None,
    top_k: int = 5,
) -> list[SubsidyMatchResult]:
    results = []
    for rule in list_policy_rules():
        condition_results = [evaluate_condition(profile, item) for item in rule.get("conditions", [])]
        missing = find_missing_inputs(profile, rule.get("required_inputs", []))
        failed = [item for item in condition_results if not item.passed and item.actual_value is not None]
        passed = [item for item in condition_results if item.passed]
        if failed:
            status = "not_eligible"
        elif missing:
            status = "possible"
        else:
            status = "eligible"
        score = _score_rule(rule, question or "", status, len(passed), len(failed), len(missing))
        results.append(
            SubsidyMatchResult(
                policy_id=rule["id"],
                policy_name=rule["name"],
                category=rule["category"],
                match_status=status,
                match_score=score,
                passed_conditions=passed,
                failed_conditions=failed,
                missing_inputs=missing,
                source_doc_id=rule.get("source_doc_id"),
            )
        )
    return sorted(results, key=lambda item: item.match_score, reverse=True)[:top_k]


def find_missing_inputs(profile: SubsidyUserProfile, required_inputs: list[dict]) -> list[RequiredInput]:
    data = profile.model_dump()
    missing = []
    for item in required_inputs:
        if not item.get("required", True):
            continue
        value = data.get(item["field"])
        if value is None or value == [] or value == "":
            missing.append(RequiredInput(**item))
    return missing


def evaluate_condition(profile: SubsidyUserProfile, condition: dict) -> ConditionResult:
    data = profile.model_dump()
    actual = data.get(condition["field"])
    expected = condition.get("value")
    op = condition.get("op")
    passed = _compare(actual, op, expected)
    return ConditionResult(
        field=condition["field"],
        label=condition.get("label", condition["field"]),
        passed=passed,
        actual_value=actual,
        expected_value=expected,
        message=condition.get("message", ""),
    )


def _compare(actual: Any, op: str, expected: Any) -> bool:
    if actual is None:
        return False
    if op == "eq":
        return actual == expected
    if op == "neq":
        return actual != expected
    if op == "in":
        return actual in expected
    if op == "not_in":
        return actual not in expected
    if op == ">=":
        return actual >= expected
    if op == ">":
        return actual > expected
    if op == "<=":
        return actual <= expected
    if op == "<":
        return actual < expected
    if op == "contains":
        return expected in (actual or [])
    if op == "contains_any":
        return bool(set(actual or []).intersection(set(expected or [])))
    if op == "between":
        return expected[0] <= actual <= expected[1]
    if op == "exists":
        return actual is not None
    return False


def _score_rule(rule: dict, question: str, status: str, passed: int, failed: int, missing: int) -> float:
    score = {"eligible": 80.0, "possible": 55.0, "not_eligible": 20.0}[status]
    score += passed * 5
    score -= failed * 8
    score -= missing * 2
    text = f"{rule.get('name', '')}{rule.get('description', '')}{' '.join(rule.get('target_tags', []))}"
    for keyword in ["毕业", "高校", "灵活就业", "社保", "创业", "开店"]:
        if keyword in question and keyword in text:
            score += 8
    return max(0, min(score, 100))

