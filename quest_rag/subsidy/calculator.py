from quest_rag.subsidy.matcher import evaluate_condition, find_missing_inputs
from quest_rag.subsidy.profile import merge_profile_with_inputs
from quest_rag.subsidy.schemas import SubsidyCalculationResult, SubsidyUserProfile
from quest_rag.subsidy.store import get_policy_rule, insert_calculation_log


def calculate_subsidy(
    policy_id: str,
    profile: SubsidyUserProfile,
    user_inputs: dict,
) -> SubsidyCalculationResult:
    rule = get_policy_rule(policy_id)
    if not rule:
        raise ValueError("补贴政策不存在")
    merged = merge_profile_with_inputs(profile, user_inputs)
    missing = find_missing_inputs(merged, rule.get("required_inputs", []))
    condition_results = [evaluate_condition(merged, item) for item in rule.get("conditions", [])]
    failed = [item for item in condition_results if not item.passed and item.actual_value is not None]
    if missing:
        result = SubsidyCalculationResult(
            policy_id=rule["id"],
            policy_name=rule["name"],
            eligible=False,
            status="missing_info",
            condition_results=condition_results,
            missing_inputs=missing,
            materials=rule.get("materials", []),
            process_steps=rule.get("process_steps", []),
            source_doc_id=rule.get("source_doc_id"),
        )
    elif failed:
        result = SubsidyCalculationResult(
            policy_id=rule["id"],
            policy_name=rule["name"],
            eligible=False,
            status="not_eligible",
            condition_results=condition_results,
            materials=rule.get("materials", []),
            process_steps=rule.get("process_steps", []),
            source_doc_id=rule.get("source_doc_id"),
        )
    else:
        amount, steps = _calculate_formula(rule.get("formula", {}), merged)
        result = SubsidyCalculationResult(
            policy_id=rule["id"],
            policy_name=rule["name"],
            eligible=True,
            status="eligible",
            estimated_amount=amount,
            condition_results=condition_results,
            calculation_steps=steps,
            materials=rule.get("materials", []),
            process_steps=rule.get("process_steps", []),
            source_doc_id=rule.get("source_doc_id"),
        )
    insert_calculation_log(profile.user_id, policy_id, user_inputs, merged.model_dump(), result.model_dump())
    return result


def _calculate_formula(formula: dict, profile: SubsidyUserProfile) -> tuple[float | None, list[str]]:
    formula_type = formula.get("type")
    if formula_type == "fixed_amount":
        amount = float(formula.get("amount", 0))
        return amount, [formula.get("formula_label") or f"固定金额：{amount:.2f} 元"]
    if formula_type == "ratio_cap":
        base = float(getattr(profile, formula.get("base_field", ""), 0) or 0)
        ratio = float(formula.get("ratio", 0))
        amount = round(base * ratio, 2)
        label = formula.get("formula_label") or "实际缴费金额 × 补贴比例"
        return amount, [
            f"实际社保缴费金额：{base:.2f} 元",
            f"补贴口径：{label}",
            f"预计补贴金额：{base:.2f} × {ratio:.4f} = {amount:.2f} 元",
            f"最长补贴期限：{formula.get('max_months')} 个月",
        ]
    if formula_type == "range_amount":
        low = float(formula.get("min", 0))
        high = float(formula.get("max", 0))
        return None, [f"预计金额区间：{low:.2f} - {high:.2f} 元"]
    return None, ["该政策暂未配置可测算公式。"]

