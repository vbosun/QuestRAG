"""
RBAC 数据访问层：角色、权限、RAG scope、用户-角色关联、工具调用日志。
"""
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


def init_permission_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_role (
                id BIGSERIAL PRIMARY KEY,
                code VARCHAR(64) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status SMALLINT NOT NULL DEFAULT 1,
                system_builtin BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_role_status ON auth_role(status)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_permission (
                id BIGSERIAL PRIMARY KEY,
                code VARCHAR(128) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                type VARCHAR(32) NOT NULL,
                resource VARCHAR(128),
                action VARCHAR(64),
                risk_level VARCHAR(32),
                group_code VARCHAR(64),
                description TEXT NOT NULL DEFAULT '',
                system_builtin BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_permission_type ON auth_permission(type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_permission_group ON auth_permission(group_code)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_account_role (
                account_id BIGINT NOT NULL REFERENCES auth_account(id) ON DELETE CASCADE,
                role_id BIGINT NOT NULL REFERENCES auth_role(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (account_id, role_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_account_role_role ON auth_account_role(role_id)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_role_permission (
                role_id BIGINT NOT NULL REFERENCES auth_role(id) ON DELETE CASCADE,
                permission_id BIGINT NOT NULL REFERENCES auth_permission(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (role_id, permission_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_role_permission_permission ON auth_role_permission(permission_id)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS rag_scope (
                id BIGSERIAL PRIMARY KEY,
                code VARCHAR(64) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status SMALLINT NOT NULL DEFAULT 1,
                system_builtin BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_role_rag_scope (
                role_id BIGINT NOT NULL REFERENCES auth_role(id) ON DELETE CASCADE,
                scope_id BIGINT NOT NULL REFERENCES rag_scope(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (role_id, scope_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_tool_call_log (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES auth_account(id) ON DELETE SET NULL,
                session_id TEXT,
                conversation_id TEXT,
                tool_name VARCHAR(128) NOT NULL,
                permission_code VARCHAR(128),
                allowed BOOLEAN NOT NULL DEFAULT false,
                deny_reason TEXT,
                requested_scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
                effective_scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
                requested_doc_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                effective_doc_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                input_summary TEXT,
                output_summary TEXT,
                latency_ms INTEGER,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_tool_call_log_user_time ON llm_tool_call_log(user_id, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_tool_call_log_tool_time ON llm_tool_call_log(tool_name, created_at DESC)")


# ── seed 辅助 ──────────────────────────────────────────────────────────

def ensure_permission(conn, code: str, name: str, type: str, group_code: str = "", risk_level: str = "LOW") -> int:
    row = conn.execute(
        "SELECT id FROM auth_permission WHERE code = %s", (code,)
    ).fetchone()
    if row:
        return row["id"]
    row = conn.execute(
        """INSERT INTO auth_permission (code, name, type, group_code, risk_level)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (code) DO NOTHING
           RETURNING id""",
        (code, name, type, group_code, risk_level),
    ).fetchone()
    if row:
        return row["id"]
    return conn.execute("SELECT id FROM auth_permission WHERE code = %s", (code,)).fetchone()["id"]


def ensure_rag_scope(conn, code: str, name: str, description: str = "") -> int:
    row = conn.execute("SELECT id FROM rag_scope WHERE code = %s", (code,)).fetchone()
    if row:
        return row["id"]
    row = conn.execute(
        """INSERT INTO rag_scope (code, name, description)
           VALUES (%s, %s, %s)
           ON CONFLICT (code) DO NOTHING
           RETURNING id""",
        (code, name, description),
    ).fetchone()
    if row:
        return row["id"]
    return conn.execute("SELECT id FROM rag_scope WHERE code = %s", (code,)).fetchone()["id"]


def ensure_role(conn, code: str, name: str, description: str = "", system_builtin: bool = False) -> dict:
    row = conn.execute("SELECT id FROM auth_role WHERE code = %s", (code,)).fetchone()
    if row:
        return {"id": row["id"], "is_new": False}
    row = conn.execute(
        """INSERT INTO auth_role (code, name, description, system_builtin)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (code) DO NOTHING
           RETURNING id""",
        (code, name, description, system_builtin),
    ).fetchone()
    if row:
        return {"id": row["id"], "is_new": True}
    rid = conn.execute("SELECT id FROM auth_role WHERE code = %s", (code,)).fetchone()["id"]
    return {"id": rid, "is_new": False}


# ── 聚合查询 ───────────────────────────────────────────────────────────

def get_user_roles(user_id: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT r.code FROM auth_role r
               JOIN auth_account_role ar ON r.id = ar.role_id
               WHERE ar.account_id = %s AND r.status = 1""",
            (user_id,),
        ).fetchall()
        return [r["code"] for r in rows]


def get_user_permissions(user_id: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT DISTINCT p.code FROM auth_permission p
               JOIN auth_role_permission rp ON p.id = rp.permission_id
               JOIN auth_account_role ar ON rp.role_id = ar.role_id
               JOIN auth_role r ON ar.role_id = r.id
               WHERE ar.account_id = %s AND r.status = 1""",
            (user_id,),
        ).fetchall()
        return sorted({r["code"] for r in rows})


def get_user_rag_scopes(user_id: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT DISTINCT s.code FROM rag_scope s
               JOIN auth_role_rag_scope rs ON s.id = rs.scope_id
               JOIN auth_account_role ar ON rs.role_id = ar.role_id
               JOIN auth_role r ON ar.role_id = r.id
               WHERE ar.account_id = %s AND r.status = 1 AND s.status = 1""",
            (user_id,),
        ).fetchall()
        return sorted({r["code"] for r in rows})


def get_aggregated_user(user_id: int) -> dict:
    return {
        "roles": get_user_roles(user_id),
        "permissions": get_user_permissions(user_id),
        "rag_scopes": get_user_rag_scopes(user_id),
    }


# ── 角色 CRUD ──────────────────────────────────────────────────────────

def list_roles() -> list[dict]:
    with get_conn() as conn:
        valid_codes = _valid_permission_codes()
        roles = conn.execute(
            """SELECT r.*,
                      (SELECT COUNT(*) FROM auth_account_role ar WHERE ar.role_id = r.id) AS user_count,
                      (SELECT COUNT(*) FROM auth_role_permission rp
                       JOIN auth_permission p ON p.id = rp.permission_id
                       WHERE rp.role_id = r.id AND p.code = ANY(%s)) AS permission_count,
                      (SELECT COUNT(*) FROM auth_role_rag_scope rs WHERE rs.role_id = r.id) AS scope_count
               FROM auth_role r
               ORDER BY r.system_builtin DESC, r.id ASC""",
            (valid_codes,),
        ).fetchall()
        return list(roles)


def create_role(code: str, name: str, description: str = "", system_builtin: bool = False) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """INSERT INTO auth_role (code, name, description, system_builtin)
               VALUES (%s, %s, %s, %s)
               RETURNING id, code, name, description, status, system_builtin, created_at, updated_at""",
            (code, name, description, system_builtin),
        ).fetchone()
        return dict(row)


def get_role(role_id: int) -> dict | None:
    with get_conn() as conn:
        valid_codes = _valid_permission_codes()
        role = conn.execute("SELECT * FROM auth_role WHERE id = %s", (role_id,)).fetchone()
        if role is None:
            return None
        role = dict(role)
        perms = conn.execute(
            "SELECT p.code, p.name, p.type, p.group_code, p.risk_level FROM auth_permission p "
            "JOIN auth_role_permission rp ON p.id = rp.permission_id "
            "WHERE rp.role_id = %s AND p.code = ANY(%s)",
            (role_id, valid_codes),
        ).fetchall()
        role["permissions"] = [dict(p) for p in perms]
        scopes = conn.execute(
            "SELECT s.code, s.name FROM rag_scope s "
            "JOIN auth_role_rag_scope rs ON s.id = rs.scope_id WHERE rs.role_id = %s",
            (role_id,),
        ).fetchall()
        role["rag_scopes"] = [dict(s) for s in scopes]
        return role


def update_role(role_id: int, name: str | None = None, description: str | None = None, status: int | None = None) -> dict | None:
    with get_conn() as conn:
        sets = []
        params = []
        if name is not None:
            sets.append("name = %s")
            params.append(name)
        if description is not None:
            sets.append("description = %s")
            params.append(description)
        if status is not None:
            sets.append("status = %s")
            params.append(status)
        if not sets:
            row = conn.execute("SELECT * FROM auth_role WHERE id = %s", (role_id,)).fetchone()
            return dict(row) if row else None
        sets.append("updated_at = now()")
        params.append(role_id)
        row = conn.execute(
            f"UPDATE auth_role SET {', '.join(sets)} WHERE id = %s RETURNING *",
            params,
        ).fetchone()
        return dict(row) if row else None


def delete_role(role_id: int) -> bool:
    with get_conn() as conn:
        result = conn.execute(
            "DELETE FROM auth_role WHERE id = %s AND system_builtin = false", (role_id,)
        )
        return result.rowcount > 0


def set_role_permissions(role_id: int, permission_codes: list[str]):
    with get_conn() as conn:
        valid_codes = set(_valid_permission_codes())
        normalized_codes = _normalize_permission_codes(permission_codes, valid_codes)
        conn.execute("DELETE FROM auth_role_permission WHERE role_id = %s", (role_id,))
        for code in normalized_codes:
            conn.execute(
                """INSERT INTO auth_role_permission (role_id, permission_id)
                   SELECT %s, id FROM auth_permission WHERE code = %s
                   ON CONFLICT DO NOTHING""",
                (role_id, code),
            )


def set_role_rag_scopes(role_id: int, scope_codes: list[str]):
    with get_conn() as conn:
        permission_rows = conn.execute(
            """SELECT p.code FROM auth_permission p
               JOIN auth_role_permission rp ON p.id = rp.permission_id
               WHERE rp.role_id = %s""",
            (role_id,),
        ).fetchall()
        permission_codes = {row["code"] for row in permission_rows}
        normalized_scopes = _normalize_rag_scope_codes(scope_codes, permission_codes)
        conn.execute("DELETE FROM auth_role_rag_scope WHERE role_id = %s", (role_id,))
        for code in normalized_scopes:
            conn.execute(
                """INSERT INTO auth_role_rag_scope (role_id, scope_id)
                   SELECT %s, id FROM rag_scope WHERE code = %s
                   ON CONFLICT DO NOTHING""",
                (role_id, code),
            )


def get_role_user_ids(role_id: int) -> list[int]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT account_id FROM auth_account_role WHERE role_id = %s", (role_id,)
        ).fetchall()
        return [r["account_id"] for r in rows]


# ── 用户管理 ───────────────────────────────────────────────────────────

def list_users(search: str = "", role_code: str = "", status: int | None = None, page: int = 1, page_size: int = 20) -> dict:
    with get_conn() as conn:
        joins = []
        wheres = []
        params: list = []

        if search:
            wheres.append("(p.full_name ILIKE %s OR a.id_number_digest ILIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])

        if role_code:
            joins.append("JOIN auth_account_role ar2 ON a.id = ar2.account_id")
            joins.append("JOIN auth_role r2 ON ar2.role_id = r2.id")
            wheres.append("r2.code = %s")
            params.append(role_code)

        if status is not None:
            wheres.append("a.status = %s")
            params.append(status)

        where_clause = ("WHERE " + " AND ".join(wheres)) if wheres else ""
        join_clause = " ".join(joins)

        count_sql = f"""SELECT COUNT(DISTINCT a.id) FROM auth_account a
                        JOIN personal_info p ON a.personal_info_id = p.id
                        {join_clause} {where_clause}"""
        total = conn.execute(count_sql, params).fetchone()["count"]

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""SELECT DISTINCT a.id, a.role as legacy_role, a.status, a.token_version,
                       a.failed_login_count, a.locked_until, a.last_login_at, a.last_login_ip,
                       a.created_at, a.updated_at,
                       p.full_name, p.id_number_ciphertext
                FROM auth_account a
                JOIN personal_info p ON a.personal_info_id = p.id
                {join_clause} {where_clause}
                ORDER BY a.id ASC
                LIMIT %s OFFSET %s""",
            params + [page_size, offset],
        ).fetchall()

        users = []
        for r in rows:
            u = dict(r)
            from quest_rag.auth.security import normalize_id_number, mask_id_number
            try:
                norm = normalize_id_number(u.get("id_number_ciphertext") or "")
                u["id_number_masked"] = mask_id_number(norm) if norm else ""
            except ValueError:
                u["id_number_masked"] = ""
            u.pop("id_number_ciphertext", None)
            u["roles"] = get_user_roles(u["id"])
            users.append(u)

        return {"items": users, "total": total, "page": page, "page_size": page_size}


def get_user_detail(user_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT a.id, a.status, a.token_version, a.failed_login_count,
                      a.locked_until, a.last_login_at, a.last_login_ip,
                      a.created_at, a.updated_at,
                      p.full_name, p.id_number_ciphertext
               FROM auth_account a
               JOIN personal_info p ON a.personal_info_id = p.id
               WHERE a.id = %s""",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        u = dict(row)
        from quest_rag.auth.security import normalize_id_number, mask_id_number
        try:
            norm = normalize_id_number(u.get("id_number_ciphertext") or "")
            u["id_number_masked"] = mask_id_number(norm) if norm else ""
        except ValueError:
            u["id_number_masked"] = ""
        u.pop("id_number_ciphertext", None)
        u["roles"] = get_user_roles(u["id"])
        return u


def set_user_roles(user_id: int, role_codes: list[str]):
    with get_conn() as conn:
        conn.execute("DELETE FROM auth_account_role WHERE account_id = %s", (user_id,))
        for code in role_codes:
            conn.execute(
                """INSERT INTO auth_account_role (account_id, role_id)
                   SELECT %s, id FROM auth_role WHERE code = %s
                   ON CONFLICT DO NOTHING""",
                (user_id, code),
            )


def update_user_status(user_id: int, status: int) -> bool:
    with get_conn() as conn:
        result = conn.execute(
            "UPDATE auth_account SET status = %s, updated_at = now() WHERE id = %s",
            (status, user_id),
        )
        return result.rowcount > 0


def lock_user(user_id: int, until: str | None = None):
    with get_conn() as conn:
        if until:
            conn.execute(
                "UPDATE auth_account SET locked_until = %s, failed_login_count = 0, updated_at = now() WHERE id = %s",
                (until, user_id),
            )
        else:
            conn.execute(
                "UPDATE auth_account SET locked_until = '2099-12-31', failed_login_count = 0, updated_at = now() WHERE id = %s",
                (user_id,),
            )


def unlock_user(user_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE auth_account SET locked_until = NULL, failed_login_count = 0, updated_at = now() WHERE id = %s",
            (user_id,),
        )


def reset_user_password(user_id: int, new_password_hash: str):
    with get_conn() as conn:
        conn.execute(
            """UPDATE auth_account
               SET password_hash = %s, token_version = token_version + 1,
                   password_changed_at = now(), updated_at = now()
               WHERE id = %s""",
            (new_password_hash, user_id),
        )


# ── session 失效 ───────────────────────────────────────────────────────

def delete_all_user_sessions(user_id: int):
    try:
        from quest_rag.auth.redis_store import delete_all_user_sessions as _redis_delete
        _redis_delete(user_id)
    except Exception:
        pass


def delete_sessions_by_role(role_id: int):
    user_ids = get_role_user_ids(role_id)
    for uid in user_ids:
        delete_all_user_sessions(uid)


# ── LLM 工具调用日志 ───────────────────────────────────────────────────

def insert_llm_tool_call_log(
    user_id: int | None = None,
    session_id: str | None = None,
    conversation_id: str | None = None,
    tool_name: str = "",
    permission_code: str = "",
    allowed: bool = False,
    deny_reason: str | None = None,
    requested_scopes: list[str] | None = None,
    effective_scopes: list[str] | None = None,
    requested_doc_ids: list[str] | None = None,
    effective_doc_ids: list[str] | None = None,
    input_summary: str | None = None,
    output_summary: str | None = None,
    latency_ms: int | None = None,
):
    import json
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO llm_tool_call_log
               (user_id, session_id, conversation_id, tool_name, permission_code,
                allowed, deny_reason, requested_scopes, effective_scopes,
                requested_doc_ids, effective_doc_ids, input_summary, output_summary, latency_ms)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                user_id, session_id, conversation_id, tool_name, permission_code,
                allowed, deny_reason,
                json.dumps(requested_scopes or []), json.dumps(effective_scopes or []),
                json.dumps(requested_doc_ids or []), json.dumps(effective_doc_ids or []),
                input_summary, output_summary, latency_ms,
            ),
        )


# ── 权限目录 ───────────────────────────────────────────────────────────

def get_permission_catalog() -> dict:
    with get_conn() as conn:
        valid_codes = _valid_permission_codes()
        perms = conn.execute(
            """SELECT code, name, type, group_code, risk_level, description
               FROM auth_permission
               WHERE code = ANY(%s)
               ORDER BY group_code, code""",
            (valid_codes,),
        ).fetchall()
        scopes = conn.execute(
            "SELECT code, name, description FROM rag_scope WHERE status = 1 ORDER BY code"
        ).fetchall()
        return {
            "permissions": [dict(p) for p in perms],
            "rag_scopes": [dict(s) for s in scopes],
            "permission_dependencies": _permission_dependencies(),
            "rag_scope_dependencies": _rag_scope_dependencies(),
            "document_rag_scope_codes": _document_rag_scope_codes(),
        }


def _valid_permission_codes() -> list[str]:
    from quest_rag.auth.permissions import PERMISSIONS

    return list(PERMISSIONS.keys())


def _permission_dependencies() -> dict[str, str]:
    from quest_rag.auth.permissions import PERMISSION_DEPENDENCIES

    return dict(PERMISSION_DEPENDENCIES)


def _rag_scope_dependencies() -> dict[str, list[str]]:
    from quest_rag.auth.permissions import RAG_SCOPE_DEPENDENCIES

    return {code: list(deps) for code, deps in RAG_SCOPE_DEPENDENCIES.items()}


def _document_rag_scope_codes() -> list[str]:
    from quest_rag.auth.permissions import DOCUMENT_RAG_SCOPE_CODES

    return sorted(DOCUMENT_RAG_SCOPE_CODES)


def _normalize_permission_codes(permission_codes: list[str], valid_codes: set[str]) -> list[str]:
    selected = {code for code in permission_codes if code in valid_codes}
    deps = _permission_dependencies()
    return sorted(
        code
        for code in selected
        if not deps.get(code) or deps[code] in selected
    )


def _normalize_rag_scope_codes(scope_codes: list[str], permission_codes: set[str]) -> list[str]:
    deps = _rag_scope_dependencies()
    selected = set(scope_codes)
    return sorted(
        code
        for code in selected
        if not deps.get(code) or any(permission in permission_codes for permission in deps[code])
    )
