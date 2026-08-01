from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from quest_rag.core.config import DATABASE_URL


@contextmanager
def get_conn():
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=5)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_auth_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS personal_info (
                id BIGSERIAL PRIMARY KEY,
                id_number_ciphertext TEXT,
                id_number_digest TEXT UNIQUE NOT NULL,
                full_name VARCHAR(50) NOT NULL,
                phone VARCHAR(20),
                gender VARCHAR(10),
                birth_date DATE,
                address TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_personal_info_id_number_digest
            ON personal_info(id_number_digest)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_account (
                id BIGSERIAL PRIMARY KEY,
                personal_info_id BIGINT NOT NULL REFERENCES personal_info(id) ON DELETE CASCADE,
                id_number_digest TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role VARCHAR(32) NOT NULL DEFAULT 'USER',
                status SMALLINT NOT NULL DEFAULT 1,
                token_version INTEGER NOT NULL DEFAULT 1,
                failed_login_count INTEGER NOT NULL DEFAULT 0,
                locked_until TIMESTAMPTZ,
                password_changed_at TIMESTAMPTZ,
                last_login_at TIMESTAMPTZ,
                last_login_ip VARCHAR(45),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_auth_account_id_number_digest
            ON auth_account(id_number_digest)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_auth_account_personal_info_id
            ON auth_account(personal_info_id)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_login_log (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES auth_account(id) ON DELETE SET NULL,
                id_number_digest TEXT,
                login_time TIMESTAMPTZ NOT NULL DEFAULT now(),
                login_ip VARCHAR(45),
                user_agent TEXT,
                status SMALLINT NOT NULL,
                fail_reason VARCHAR(100)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_auth_login_log_user_time
            ON auth_login_log(user_id, login_time DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_auth_login_log_digest_time
            ON auth_login_log(id_number_digest, login_time DESC)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_operation_log (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES auth_account(id) ON DELETE SET NULL,
                action VARCHAR(80) NOT NULL,
                target_type VARCHAR(80),
                target_id TEXT,
                request_ip VARCHAR(45),
                user_agent TEXT,
                detail JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_auth_operation_log_user_time
            ON auth_operation_log(user_id, created_at DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_auth_operation_log_action_time
            ON auth_operation_log(action, created_at DESC)
        """)


def get_account_by_id_number_digest(digest: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT a.id, a.personal_info_id, a.id_number_digest, a.password_hash,
                      a.role, a.status, a.token_version, a.failed_login_count,
                      a.locked_until, a.password_changed_at, a.last_login_at, a.last_login_ip,
                      p.full_name, p.id_number_ciphertext
               FROM auth_account a
               JOIN personal_info p ON a.personal_info_id = p.id
               WHERE a.id_number_digest = %s""",
            (digest,),
        ).fetchone()
        return row if row else None


def get_account_by_id(user_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT a.id, a.personal_info_id, a.id_number_digest, a.password_hash,
                      a.role, a.status, a.token_version, a.failed_login_count,
                      a.locked_until, a.password_changed_at, a.last_login_at, a.last_login_ip,
                      p.full_name, p.id_number_ciphertext
               FROM auth_account a
               JOIN personal_info p ON a.personal_info_id = p.id
               WHERE a.id = %s""",
            (user_id,),
        ).fetchone()
        return row if row else None


def update_last_login(user_id: int, login_ip: str | None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE auth_account SET last_login_at = now(), last_login_ip = %s, failed_login_count = 0, locked_until = NULL, updated_at = now() WHERE id = %s",
            (login_ip, user_id),
        )


def increment_failed_login(digest: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE auth_account SET failed_login_count = failed_login_count + 1, updated_at = now() WHERE id_number_digest = %s",
            (digest,),
        )


def insert_login_log(
    user_id: int | None,
    id_number_digest: str | None,
    login_ip: str | None,
    user_agent: str | None,
    status: int,
    fail_reason: str | None = None,
):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO auth_login_log (user_id, id_number_digest, login_ip, user_agent, status, fail_reason)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (user_id, id_number_digest, login_ip, user_agent, status, fail_reason),
        )


def insert_operation_log(
    user_id: int,
    action: str,
    request_ip: str | None = None,
    user_agent: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict | None = None,
):
    import json

    with get_conn() as conn:
        conn.execute(
            """INSERT INTO auth_operation_log (user_id, action, target_type, target_id, request_ip, user_agent, detail)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (user_id, action, target_type, target_id, request_ip, user_agent, json.dumps(detail or {})),
        )


def update_password(user_id: int, new_password_hash: str):
    with get_conn() as conn:
        conn.execute(
            """UPDATE auth_account
               SET password_hash = %s, token_version = token_version + 1,
                   password_changed_at = now(), updated_at = now()
               WHERE id = %s""",
            (new_password_hash, user_id),
        )


def get_token_version(user_id: int) -> int | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT token_version FROM auth_account WHERE id = %s",
            (user_id,),
        ).fetchone()
        return row["token_version"] if row else None


def create_personal_info(id_number_digest: str, full_name: str, id_number: str | None = None) -> int:
    with get_conn() as conn:
        row = conn.execute(
            """INSERT INTO personal_info (id_number_digest, full_name, id_number_ciphertext)
               VALUES (%s, %s, %s)
               ON CONFLICT (id_number_digest) DO UPDATE SET full_name = EXCLUDED.full_name, updated_at = now()
               RETURNING id""",
            (id_number_digest, full_name, id_number),
        ).fetchone()
        return row["id"]


def create_auth_account(personal_info_id: int, id_number_digest: str, password_hash: str, role: str = "USER") -> int:
    with get_conn() as conn:
        row = conn.execute(
            """INSERT INTO auth_account (personal_info_id, id_number_digest, password_hash, role)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (id_number_digest) DO NOTHING
               RETURNING id""",
            (personal_info_id, id_number_digest, password_hash, role),
        ).fetchone()
        if row:
            return row["id"]
        existing = conn.execute(
            "SELECT id FROM auth_account WHERE id_number_digest = %s",
            (id_number_digest,),
        ).fetchone()
        return existing["id"] if existing else 0
