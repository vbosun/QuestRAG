"""PostgreSQL persistence for application cases.

The values table is intentionally isolated from the general chat-memory tables so a later
envelope-encryption implementation can be introduced without changing workflow records.
"""

import json
import uuid
from psycopg.errors import InvalidTextRepresentation

from quest_rag.auth.store import get_conn


def init_application_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS application_case (
                id UUID PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES auth_account(id) ON DELETE CASCADE,
                business_code VARCHAR(100) NOT NULL,
                definition_version VARCHAR(100) NOT NULL,
                status VARCHAR(40) NOT NULL,
                current_step VARCHAR(100) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS application_draft_field (
                case_id UUID NOT NULL REFERENCES application_case(id) ON DELETE CASCADE,
                field_key VARCHAR(120) NOT NULL,
                value JSONB,
                source VARCHAR(40) NOT NULL,
                revision INTEGER NOT NULL DEFAULT 0,
                sync_state VARCHAR(30) NOT NULL DEFAULT 'pending',
                last_browser_value_hash VARCHAR(128),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (case_id, field_key)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS application_browser_connection (
                case_id UUID PRIMARY KEY REFERENCES application_case(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL REFERENCES auth_account(id) ON DELETE CASCADE,
                device_name VARCHAR(100) NOT NULL,
                status VARCHAR(30) NOT NULL,
                adapter_id VARCHAR(120) NOT NULL,
                entry_url TEXT NOT NULL,
                last_page VARCHAR(120),
                last_error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS application_attachment (
                id UUID PRIMARY KEY,
                case_id UUID NOT NULL REFERENCES application_case(id) ON DELETE CASCADE,
                material_key VARCHAR(120) NOT NULL,
                original_name TEXT NOT NULL,
                content_type VARCHAR(200),
                size_bytes BIGINT NOT NULL,
                content BYTEA NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS application_action_log (
                id BIGSERIAL PRIMARY KEY,
                case_id UUID NOT NULL REFERENCES application_case(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL REFERENCES auth_account(id) ON DELETE CASCADE,
                action VARCHAR(80) NOT NULL,
                detail JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_application_case_user_updated ON application_case(user_id, updated_at DESC)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS application_workflow_task (
                id BIGSERIAL PRIMARY KEY,
                case_id UUID NOT NULL REFERENCES application_case(id) ON DELETE CASCADE,
                node_code VARCHAR(100) NOT NULL,
                assignee_role VARCHAR(80),
                status VARCHAR(30) NOT NULL,
                comment TEXT,
                acted_by BIGINT REFERENCES auth_account(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                acted_at TIMESTAMPTZ
            )
        """)


def create_case(user_id: int, business_code: str, version: str, status: str, step: str) -> dict:
    case_id = str(uuid.uuid4())
    with get_conn() as conn:
        return conn.execute(
            """INSERT INTO application_case (id, user_id, business_code, definition_version, status, current_step)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
            (case_id, user_id, business_code, version, status, step),
        ).fetchone()


def get_case(user_id: int, case_id: str) -> dict | None:
    with get_conn() as conn:
        try:
            return conn.execute("SELECT * FROM application_case WHERE id = %s AND user_id = %s", (case_id, user_id)).fetchone()
        except InvalidTextRepresentation:
            # A stale/hallucinated artifact id must become a normal not-found
            # result, never an unhandled 500 from PostgreSQL.
            return None


def list_cases(user_id: int) -> list[dict]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM application_case WHERE user_id = %s ORDER BY updated_at DESC", (user_id,)).fetchall()


def get_fields(case_id: str) -> list[dict]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM application_draft_field WHERE case_id = %s ORDER BY field_key", (case_id,)).fetchall()


def get_field(case_id: str, field_key: str) -> dict | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM application_draft_field WHERE case_id = %s AND field_key = %s", (case_id, field_key)).fetchone()


def upsert_field(case_id: str, field_key: str, value, source: str, sync_state: str, revision: int) -> dict:
    with get_conn() as conn:
        return conn.execute(
            """INSERT INTO application_draft_field (case_id, field_key, value, source, sync_state, revision)
               VALUES (%s, %s, %s::jsonb, %s, %s, %s)
               ON CONFLICT (case_id, field_key) DO UPDATE SET
                 value = EXCLUDED.value, source = EXCLUDED.source, sync_state = EXCLUDED.sync_state,
                 revision = EXCLUDED.revision, updated_at = now()
               RETURNING *""",
            (case_id, field_key, json.dumps(value, ensure_ascii=False), source, sync_state, revision),
        ).fetchone()


def update_case(case_id: str, status: str, current_step: str) -> dict:
    with get_conn() as conn:
        return conn.execute(
            "UPDATE application_case SET status = %s, current_step = %s, updated_at = now() WHERE id = %s RETURNING *",
            (status, current_step, case_id),
        ).fetchone()


def upsert_browser_connection(case_id: str, user_id: int, device_name: str, adapter_id: str, entry_url: str) -> dict:
    with get_conn() as conn:
        return conn.execute(
            """INSERT INTO application_browser_connection (case_id, user_id, device_name, status, adapter_id, entry_url, last_page)
               VALUES (%s, %s, %s, 'connected', %s, %s, 'application_form')
               ON CONFLICT (case_id) DO UPDATE SET device_name = EXCLUDED.device_name, status = 'connected',
                 adapter_id = EXCLUDED.adapter_id, entry_url = EXCLUDED.entry_url, last_error = NULL, updated_at = now()
               RETURNING *""",
            (case_id, user_id, device_name, adapter_id, entry_url),
        ).fetchone()


def get_browser_connection(case_id: str) -> dict | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM application_browser_connection WHERE case_id = %s", (case_id,)).fetchone()


def add_attachment(case_id: str, material_key: str, original_name: str, content_type: str | None, content: bytes) -> dict:
    attachment_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute("DELETE FROM application_attachment WHERE case_id = %s AND material_key = %s", (case_id, material_key))
        return conn.execute(
            """INSERT INTO application_attachment (id, case_id, material_key, original_name, content_type, size_bytes, content)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id, material_key, original_name, content_type, size_bytes, created_at""",
            (attachment_id, case_id, material_key, original_name, content_type, len(content), content),
        ).fetchone()


def get_attachments(case_id: str) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, material_key, original_name, content_type, size_bytes, created_at FROM application_attachment WHERE case_id = %s ORDER BY created_at DESC",
            (case_id,),
        ).fetchall()


def log_action(case_id: str, user_id: int, action: str, detail: dict | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO application_action_log (case_id, user_id, action, detail) VALUES (%s, %s, %s, %s::jsonb)",
            (case_id, user_id, action, json.dumps(detail or {}, ensure_ascii=False)),
        )


def create_workflow_task(case_id: str, node_code: str, assignee_role: str | None, status: str = "PENDING") -> dict:
    with get_conn() as conn:
        return conn.execute(
            """INSERT INTO application_workflow_task (case_id, node_code, assignee_role, status)
               VALUES (%s, %s, %s, %s) RETURNING *""",
            (case_id, node_code, assignee_role, status),
        ).fetchone()


def get_workflow_tasks(case_id: str) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM application_workflow_task WHERE case_id = %s ORDER BY id", (case_id,)
        ).fetchall()


def get_pending_workflow_task(case_id: str) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM application_workflow_task WHERE case_id = %s AND status = 'PENDING' ORDER BY id LIMIT 1",
            (case_id,),
        ).fetchone()


def complete_workflow_task(task_id: int, status: str, acted_by: int, comment: str | None = None) -> dict:
    with get_conn() as conn:
        return conn.execute(
            """UPDATE application_workflow_task SET status = %s, acted_by = %s, comment = %s, acted_at = now()
               WHERE id = %s RETURNING *""",
            (status, acted_by, comment, task_id),
        ).fetchone()
