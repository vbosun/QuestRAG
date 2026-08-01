import json
import uuid
from typing import Any

from psycopg.types.json import Jsonb

from quest_rag.auth.store import get_conn


def init_subsidy_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subsidy_policy (
                id TEXT PRIMARY KEY,
                code VARCHAR(80) UNIQUE NOT NULL,
                name VARCHAR(160) NOT NULL,
                category VARCHAR(64) NOT NULL,
                region VARCHAR(80),
                status SMALLINT NOT NULL DEFAULT 1,
                source_doc_id TEXT,
                source_title TEXT,
                effective_start DATE,
                effective_end DATE,
                description TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_subsidy_policy_category ON subsidy_policy(category)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subsidy_rule (
                id TEXT PRIMARY KEY,
                policy_id TEXT NOT NULL REFERENCES subsidy_policy(id) ON DELETE CASCADE,
                version VARCHAR(40) NOT NULL DEFAULT 'v1',
                target_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
                required_inputs JSONB NOT NULL DEFAULT '[]'::jsonb,
                conditions JSONB NOT NULL DEFAULT '[]'::jsonb,
                formula JSONB NOT NULL DEFAULT '{}'::jsonb,
                materials JSONB NOT NULL DEFAULT '[]'::jsonb,
                process_steps JSONB NOT NULL DEFAULT '[]'::jsonb,
                notes TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_subsidy_rule_policy ON subsidy_rule(policy_id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subsidy_calculation_log (
                id TEXT PRIMARY KEY,
                user_id BIGINT REFERENCES auth_account(id) ON DELETE SET NULL,
                policy_id TEXT REFERENCES subsidy_policy(id) ON DELETE SET NULL,
                input_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
                profile_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
                result JSONB NOT NULL DEFAULT '{}'::jsonb,
                status VARCHAR(32) NOT NULL DEFAULT 'completed',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_subsidy_calculation_log_user_time
            ON subsidy_calculation_log(user_id, created_at DESC)
        """)


def seed_subsidy_rules() -> None:
    for policy in _seed_policies():
        upsert_policy_with_rule(policy)


def upsert_policy_with_rule(policy: dict[str, Any]) -> None:
    rule = policy.pop("rule")
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO subsidy_policy
               (id, code, name, category, region, source_doc_id, source_title, description)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET
                 name = EXCLUDED.name,
                 category = EXCLUDED.category,
                 region = EXCLUDED.region,
                 source_doc_id = EXCLUDED.source_doc_id,
                 source_title = EXCLUDED.source_title,
                 description = EXCLUDED.description,
                 updated_at = now()""",
            (
                policy["id"], policy["code"], policy["name"], policy["category"],
                policy.get("region"), policy.get("source_doc_id"),
                policy.get("source_title"), policy.get("description", ""),
            ),
        )
        conn.execute(
            """INSERT INTO subsidy_rule
               (id, policy_id, target_tags, required_inputs, conditions, formula, materials, process_steps, notes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET
                 target_tags = EXCLUDED.target_tags,
                 required_inputs = EXCLUDED.required_inputs,
                 conditions = EXCLUDED.conditions,
                 formula = EXCLUDED.formula,
                 materials = EXCLUDED.materials,
                 process_steps = EXCLUDED.process_steps,
                 notes = EXCLUDED.notes,
                 updated_at = now()""",
            (
                rule["id"], policy["id"],
                Jsonb(rule.get("target_tags", [])),
                Jsonb(rule.get("required_inputs", [])),
                Jsonb(rule.get("conditions", [])),
                Jsonb(rule.get("formula", {})),
                Jsonb(rule.get("materials", [])),
                Jsonb(rule.get("process_steps", [])),
                rule.get("notes", ""),
            ),
        )


def list_policy_rules() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT p.*, r.id AS rule_id, r.target_tags, r.required_inputs, r.conditions,
                      r.formula, r.materials, r.process_steps, r.notes
               FROM subsidy_policy p
               JOIN subsidy_rule r ON p.id = r.policy_id
               WHERE p.status = 1
               ORDER BY p.category, p.name"""
        ).fetchall()
        return [_normalize_rule_row(dict(row)) for row in rows]


def get_policy_rule(policy_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT p.*, r.id AS rule_id, r.target_tags, r.required_inputs, r.conditions,
                      r.formula, r.materials, r.process_steps, r.notes
               FROM subsidy_policy p
               JOIN subsidy_rule r ON p.id = r.policy_id
               WHERE p.id = %s AND p.status = 1""",
            (policy_id,),
        ).fetchone()
        return _normalize_rule_row(dict(row)) if row else None


def insert_calculation_log(user_id: int, policy_id: str, user_inputs: dict, profile: dict, result: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO subsidy_calculation_log
               (id, user_id, policy_id, input_snapshot, profile_snapshot, result, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                str(uuid.uuid4()), user_id, policy_id,
                Jsonb(user_inputs),
                Jsonb(profile),
                Jsonb(result),
                result.get("status", "completed"),
            ),
        )


def list_calculation_logs(user_id: int, limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT l.*, p.name AS policy_name
               FROM subsidy_calculation_log l
               LEFT JOIN subsidy_policy p ON l.policy_id = p.id
               WHERE l.user_id = %s
               ORDER BY l.created_at DESC
               LIMIT %s""",
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def _normalize_rule_row(row: dict[str, Any]) -> dict[str, Any]:
    for key in ["target_tags", "required_inputs", "conditions", "formula", "materials", "process_steps"]:
        value = row.get(key)
        if isinstance(value, str):
            row[key] = json.loads(value)
    return row


def _seed_policies() -> list[dict[str, Any]]:
    common_social_materials = ["身份证", "社会保障卡", "《就业创业证》", "当年度社会保险缴费凭证", "灵活就业登记材料"]
    common_social_steps = ["灵活就业登记", "缴纳社会保险费", "提交补贴申请", "经办机构审核公示", "拨付到社保卡账户"]
    return [
        {
            "id": "subsidy_flexible_employment_difficulty_social_insurance",
            "code": "flexible_employment_difficulty_social_insurance",
            "name": "灵活就业社保补贴（就业困难人员）",
            "category": "social_insurance_subsidy",
            "region": "甘肃省",
            "source_doc_id": "甘财社〔2024〕152号",
            "source_title": "甘肃省就业补助资金管理办法",
            "description": "就业困难人员灵活就业并缴纳社会保险费后，按实际缴费额一定比例补贴。",
            "rule": {
                "id": "rule_flexible_employment_difficulty_social_insurance_v1",
                "target_tags": ["flexible_employment", "employment_difficulty_person"],
                "required_inputs": [
                    {"field": "employment_status", "label": "就业状态", "source": "user_input", "required": True},
                    {"field": "person_tags", "label": "人员类别", "source": "user_input", "required": True},
                    {"field": "social_insurance_months", "label": "社保缴费月数", "source": "social_security", "required": True},
                    {"field": "actual_social_insurance_payment", "label": "实际社保缴费金额", "source": "social_security", "required": True},
                ],
                "conditions": [
                    {"field": "employment_status", "label": "就业状态", "op": "eq", "value": "flexible_employment", "message": "需已办理灵活就业登记"},
                    {"field": "person_tags", "label": "人员类别", "op": "contains", "value": "employment_difficulty_person", "message": "需属于就业困难人员"},
                    {"field": "social_insurance_months", "label": "社保缴费月数", "op": ">", "value": 0, "message": "需以灵活就业人员身份缴纳社会保险费"},
                ],
                "formula": {"type": "ratio_cap", "base_field": "actual_social_insurance_payment", "ratio": 0.6667, "max_months": 36, "formula_label": "实际缴费金额 × 2/3"},
                "materials": common_social_materials + ["《就业困难人员认定申请表》"],
                "process_steps": ["就业困难人员认定"] + common_social_steps,
            },
        },
        {
            "id": "subsidy_college_graduate_flexible_social_insurance",
            "code": "college_graduate_flexible_social_insurance",
            "name": "高校毕业生灵活就业社保补贴",
            "category": "social_insurance_subsidy",
            "region": "甘肃省",
            "source_doc_id": "甘财社〔2024〕152号",
            "source_title": "甘肃省就业补助资金管理办法",
            "description": "离校2年内未就业高校毕业生灵活就业并缴纳社会保险费后，可申请社保补贴。",
            "rule": {
                "id": "rule_college_graduate_flexible_social_insurance_v1",
                "target_tags": ["college_graduate_within_2_years", "flexible_employment"],
                "required_inputs": [
                    {"field": "is_college_graduate", "label": "是否高校毕业生", "source": "user_input", "required": True},
                    {"field": "graduation_year", "label": "毕业年份", "source": "user_input", "required": True},
                    {"field": "employment_status", "label": "就业状态", "source": "user_input", "required": True},
                    {"field": "actual_social_insurance_payment", "label": "实际社保缴费金额", "source": "social_security", "required": True},
                ],
                "conditions": [
                    {"field": "is_college_graduate", "label": "是否高校毕业生", "op": "eq", "value": True, "message": "需为高校毕业生"},
                    {"field": "graduation_year", "label": "毕业年份", "op": ">=", "value": 2024, "message": "需属于离校2年内高校毕业生"},
                    {"field": "employment_status", "label": "就业状态", "op": "eq", "value": "flexible_employment", "message": "需已办理灵活就业登记"},
                ],
                "formula": {"type": "ratio_cap", "base_field": "actual_social_insurance_payment", "ratio": 0.6667, "max_months": 24, "formula_label": "实际缴费金额 × 2/3"},
                "materials": common_social_materials + ["毕业证书", "个人材料真实性承诺书"],
                "process_steps": common_social_steps,
            },
        },
        {
            "id": "subsidy_one_time_entrepreneurship",
            "code": "one_time_entrepreneurship",
            "name": "一次性创业补贴",
            "category": "entrepreneurship_subsidy",
            "region": "甘肃省",
            "source_doc_id": "甘财社〔2024〕152号",
            "source_title": "甘肃省就业补助资金管理办法",
            "description": "首次创办小微企业或从事个体经营并正常运营1年以上的重点群体，可申请一次性补贴。",
            "rule": {
                "id": "rule_one_time_entrepreneurship_v1",
                "target_tags": ["entrepreneurship"],
                "required_inputs": [
                    {"field": "first_business", "label": "是否首次创业", "source": "user_input", "required": True},
                    {"field": "business_status", "label": "经营状态", "source": "user_input", "required": True},
                    {"field": "business_months", "label": "正常经营月数", "source": "user_input", "required": True},
                    {"field": "person_tags", "label": "人员类别", "source": "user_input", "required": True},
                ],
                "conditions": [
                    {"field": "first_business", "label": "是否首次创业", "op": "eq", "value": True, "message": "需首次创办小微企业或从事个体经营"},
                    {"field": "business_status", "label": "经营状态", "op": "eq", "value": "active", "message": "当前需正常经营"},
                    {"field": "business_months", "label": "正常经营月数", "op": ">=", "value": 12, "message": "需正常运营1年以上"},
                    {"field": "person_tags", "label": "人员类别", "op": "contains_any", "value": ["employment_difficulty_person", "college_graduate_within_2_years", "returning_entrepreneur", "veteran"], "message": "需属于就业困难人员、离校2年内高校毕业生、返乡入乡创业人员或就业困难退役军人之一"},
                ],
                "formula": {"type": "fixed_amount", "amount": 5000, "formula_label": "一次性补贴 5000 元"},
                "materials": ["身份证", "营业执照正副本复印件", "个人真实性承诺书"],
                "process_steps": ["准备申请材料", "向当地人社部门提交申请", "人社部门审核", "拨付到社保卡银行账户"],
            },
        },
    ]
