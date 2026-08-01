from datetime import date
from decimal import Decimal

from psycopg.types.json import Jsonb

from quest_rag.auth.store import get_conn


def init_social_security_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS social_security_profile (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES auth_account(id) ON DELETE CASCADE,
                id_number_digest TEXT NOT NULL,
                social_security_no VARCHAR(64),
                insured_status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
                insured_unit VARCHAR(160),
                first_insured_date DATE,
                current_base NUMERIC(12, 2),
                total_payment_months INTEGER NOT NULL DEFAULT 0,
                pension_account_balance NUMERIC(12, 2) NOT NULL DEFAULT 0,
                medical_account_balance NUMERIC(12, 2) NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_social_security_profile_user ON social_security_profile(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_social_security_profile_digest ON social_security_profile(id_number_digest)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS social_security_payment_record (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES auth_account(id) ON DELETE CASCADE,
                payment_month VARCHAR(7) NOT NULL,
                insurance_type VARCHAR(32) NOT NULL,
                payment_base NUMERIC(12, 2) NOT NULL DEFAULT 0,
                personal_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
                company_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
                total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
                paid_status VARCHAR(32) NOT NULL DEFAULT 'PAID',
                paid_at DATE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_social_security_payment_user_month
            ON social_security_payment_record(user_id, payment_month DESC)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS social_security_access_log (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES auth_account(id) ON DELETE SET NULL,
                action VARCHAR(80) NOT NULL,
                query_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)


def seed_social_security_data() -> None:
    with get_conn() as conn:
        accounts = conn.execute(
            "SELECT id, id_number_digest FROM auth_account ORDER BY id ASC LIMIT 5"
        ).fetchall()
        for index, account in enumerate(accounts):
            existing = conn.execute(
                "SELECT id FROM social_security_profile WHERE user_id = %s",
                (account["id"],),
            ).fetchone()
            if existing:
                continue
            months = 8 if index == 0 else 3 if index == 1 else 36
            base = Decimal("4200.00") if index != 2 else Decimal("6500.00")
            unit = "灵活就业人员参保" if index in {0, 1} else "兰州某某服务有限公司"
            conn.execute(
                """INSERT INTO social_security_profile
                   (user_id, id_number_digest, social_security_no, insured_status, insured_unit,
                    first_insured_date, current_base, total_payment_months,
                    pension_account_balance, medical_account_balance)
                   VALUES (%s, %s, %s, 'ACTIVE', %s, %s, %s, %s, %s, %s)""",
                (
                    account["id"], account["id_number_digest"], f"SSN{account['id']:08d}",
                    unit, date(2025, 12, 1), base, months,
                    base * Decimal("0.08") * months,
                    base * Decimal("0.02") * months,
                ),
            )
            for offset in range(months):
                year = 2026 if offset < 7 else 2025
                month = 7 - offset if offset < 7 else 12 - (offset - 7)
                payment_month = f"{year}-{month:02d}"
                conn.execute(
                    """INSERT INTO social_security_payment_record
                       (user_id, payment_month, insurance_type, payment_base,
                        personal_amount, company_amount, total_amount, paid_at)
                       VALUES (%s, %s, 'PENSION', %s, %s, %s, %s, %s)""",
                    (
                        account["id"], payment_month, base,
                        base * Decimal("0.08"), base * Decimal("0.16"),
                        base * Decimal("0.24"), date(year, month, 20),
                    ),
                )
                conn.execute(
                    """INSERT INTO social_security_payment_record
                       (user_id, payment_month, insurance_type, payment_base,
                        personal_amount, company_amount, total_amount, paid_at)
                       VALUES (%s, %s, 'MEDICAL', %s, %s, %s, %s, %s)""",
                    (
                        account["id"], payment_month, base,
                        base * Decimal("0.02"), base * Decimal("0.08"),
                        base * Decimal("0.10"), date(year, month, 20),
                    ),
                )


def get_profile(user_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT insured_status, insured_unit, first_insured_date, current_base,
                      total_payment_months, pension_account_balance, medical_account_balance, updated_at
               FROM social_security_profile WHERE user_id = %s""",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def list_payment_records(
    user_id: int,
    insurance_type: str | None = None,
    start_month: str | None = None,
    end_month: str | None = None,
    limit: int = 24,
) -> list[dict]:
    wheres = ["user_id = %s"]
    params: list = [user_id]
    if insurance_type:
        wheres.append("insurance_type = %s")
        params.append(insurance_type)
    if start_month:
        wheres.append("payment_month >= %s")
        params.append(start_month)
    if end_month:
        wheres.append("payment_month <= %s")
        params.append(end_month)
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT payment_month, insurance_type, payment_base, personal_amount,
                       company_amount, total_amount, paid_status, paid_at
                FROM social_security_payment_record
                WHERE {' AND '.join(wheres)}
                ORDER BY payment_month DESC, insurance_type ASC
                LIMIT %s""",
            params,
        ).fetchall()
        return [dict(row) for row in rows]


def insert_access_log(user_id: int, action: str, query_summary: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO social_security_access_log (user_id, action, query_summary)
               VALUES (%s, %s, %s)""",
            (user_id, action, Jsonb(query_summary)),
        )
