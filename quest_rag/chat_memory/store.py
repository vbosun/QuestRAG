import json
import uuid
from typing import Any

from psycopg.types.json import Jsonb

from quest_rag.auth.store import get_conn

_initialized = False


def init_chat_memory_db() -> None:
    global _initialized
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_conversation (
                id TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES auth_account(id) ON DELETE CASCADE,
                title VARCHAR(160) NOT NULL DEFAULT '新会话',
                status SMALLINT NOT NULL DEFAULT 1,
                next_sequence INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_conversation_user_time
            ON chat_conversation(user_id, updated_at DESC)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_message (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES chat_conversation(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL REFERENCES auth_account(id) ON DELETE CASCADE,
                sequence INTEGER NOT NULL,
                role VARCHAR(32) NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                raw TEXT NOT NULL DEFAULT '',
                parts JSONB NOT NULL DEFAULT '[]'::jsonb,
                citations JSONB NOT NULL DEFAULT '[]'::jsonb,
                status VARCHAR(32) NOT NULL DEFAULT 'completed',
                error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (conversation_id, sequence)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_message_conversation_sequence
            ON chat_message(conversation_id, sequence ASC)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_tool_memory (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES chat_conversation(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL REFERENCES auth_account(id) ON DELETE CASCADE,
                sequence INTEGER NOT NULL,
                tool_name VARCHAR(128) NOT NULL,
                memory_type VARCHAR(80) NOT NULL,
                facts JSONB NOT NULL DEFAULT '{}'::jsonb,
                input_summary TEXT,
                output_summary TEXT,
                source_message_id TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (conversation_id, sequence)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_tool_memory_conversation_sequence
            ON chat_tool_memory(conversation_id, sequence ASC)
        """)
    _initialized = True


def ensure_chat_memory_db() -> None:
    if not _initialized:
        init_chat_memory_db()


def create_conversation(user_id: int, title: str = "新会话", conversation_id: str | None = None) -> dict:
    ensure_chat_memory_db()
    conversation_id = conversation_id or str(uuid.uuid4())
    with get_conn() as conn:
        row = conn.execute(
            """INSERT INTO chat_conversation (id, user_id, title)
               VALUES (%s, %s, %s)
               RETURNING id, title, created_at, updated_at""",
            (conversation_id, user_id, title[:160] or "新会话"),
        ).fetchone()
        return dict(row)


def ensure_conversation(user_id: int, conversation_id: str | None, title: str = "新会话") -> dict:
    if conversation_id:
        existing = get_conversation(user_id, conversation_id)
        if existing:
            return existing
        return create_conversation(user_id, title, conversation_id)
    return create_conversation(user_id, title)


def get_conversation(user_id: int, conversation_id: str) -> dict | None:
    ensure_chat_memory_db()
    with get_conn() as conn:
        row = conn.execute(
            """SELECT id, title, created_at, updated_at
               FROM chat_conversation
               WHERE id = %s AND user_id = %s AND status = 1""",
            (conversation_id, user_id),
        ).fetchone()
        return dict(row) if row else None


def list_conversations(user_id: int, page: int = 1, page_size: int = 30) -> dict:
    ensure_chat_memory_db()
    page = max(page, 1)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM chat_conversation WHERE user_id = %s AND status = 1",
            (user_id,),
        ).fetchone()["count"]
        rows = conn.execute(
            """SELECT id, title, created_at, updated_at
               FROM chat_conversation
               WHERE user_id = %s AND status = 1
               ORDER BY updated_at DESC
               LIMIT %s OFFSET %s""",
            (user_id, page_size, offset),
        ).fetchall()
        return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}


def delete_conversation(user_id: int, conversation_id: str) -> bool:
    ensure_chat_memory_db()
    with get_conn() as conn:
        result = conn.execute(
            "DELETE FROM chat_conversation WHERE id = %s AND user_id = %s",
            (conversation_id, user_id),
        )
        return result.rowcount > 0


def rename_conversation(user_id: int, conversation_id: str, title: str) -> dict | None:
    ensure_chat_memory_db()
    with get_conn() as conn:
        row = conn.execute(
            """UPDATE chat_conversation
               SET title = %s, updated_at = now()
               WHERE id = %s AND user_id = %s
               RETURNING id, title, created_at, updated_at""",
            (title[:160] or "新会话", conversation_id, user_id),
        ).fetchone()
        return dict(row) if row else None


def insert_message(
    user_id: int,
    conversation_id: str,
    role: str,
    content: str,
    raw: str | None = None,
    parts: list[dict] | None = None,
    citations: list[dict] | None = None,
    status: str = "completed",
    error: str | None = None,
) -> dict:
    ensure_chat_memory_db()
    message_id = str(uuid.uuid4())
    with get_conn() as conn:
        sequence = _next_sequence(conn, conversation_id, user_id)
        row = conn.execute(
            """INSERT INTO chat_message
               (id, conversation_id, user_id, sequence, role, content, raw, parts, citations, status, error)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id, conversation_id, sequence, role, content, raw, parts, citations, status, error, created_at""",
            (
                message_id, conversation_id, user_id, sequence, role, content, raw or content,
                Jsonb(parts or ([] if not content else [{"type": "markdown", "content": content}])),
                Jsonb(citations or []), status, error,
            ),
        ).fetchone()
        _touch_conversation(conn, conversation_id, title=content[:24] if role == "user" else None)
        return dict(row)


def insert_tool_memory(
    user_id: int,
    conversation_id: str,
    tool_name: str,
    memory_type: str,
    facts: dict,
    input_summary: str | None = None,
    output_summary: str | None = None,
    source_message_id: str | None = None,
) -> dict | None:
    ensure_chat_memory_db()
    if not conversation_id:
        return None
    memory_id = str(uuid.uuid4())
    with get_conn() as conn:
        sequence = _next_sequence(conn, conversation_id, user_id)
        row = conn.execute(
            """INSERT INTO chat_tool_memory
               (id, conversation_id, user_id, sequence, tool_name, memory_type, facts,
                input_summary, output_summary, source_message_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id, conversation_id, sequence, tool_name, memory_type, facts,
                         input_summary, output_summary, created_at, updated_at""",
            (
                memory_id, conversation_id, user_id, sequence, tool_name, memory_type,
                Jsonb(facts), input_summary, output_summary, source_message_id,
            ),
        ).fetchone()
        _touch_conversation(conn, conversation_id)
        return dict(row)


def get_conversation_detail(user_id: int, conversation_id: str) -> dict | None:
    ensure_chat_memory_db()
    conversation = get_conversation(user_id, conversation_id)
    if not conversation:
        return None
    with get_conn() as conn:
        messages = conn.execute(
            """SELECT id, sequence, role, content, raw, parts, citations, status, error, created_at
               FROM chat_message
               WHERE conversation_id = %s AND user_id = %s
               ORDER BY sequence ASC""",
            (conversation_id, user_id),
        ).fetchall()
        memories = conn.execute(
            """SELECT id, sequence, tool_name, memory_type, facts, input_summary, output_summary, created_at
               FROM chat_tool_memory
               WHERE conversation_id = %s AND user_id = %s
               ORDER BY sequence ASC""",
            (conversation_id, user_id),
        ).fetchall()
    conversation["messages"] = [dict(row) for row in messages]
    conversation["tool_memories"] = [dict(row) for row in memories]
    return conversation


def load_memory_context(user_id: int, conversation_id: str, message_limit: int = 10, memory_limit: int = 8) -> str:
    ensure_chat_memory_db()
    with get_conn() as conn:
        messages = conn.execute(
            """SELECT role, content FROM chat_message
               WHERE conversation_id = %s AND user_id = %s
               ORDER BY sequence DESC
               LIMIT %s""",
            (conversation_id, user_id, message_limit),
        ).fetchall()
        memories = conn.execute(
            """SELECT tool_name, memory_type, facts FROM chat_tool_memory
               WHERE conversation_id = %s AND user_id = %s
               ORDER BY sequence DESC
               LIMIT %s""",
            (conversation_id, user_id, memory_limit),
        ).fetchall()
    lines = []
    if messages:
        lines.append("当前会话最近对话：")
        for item in reversed(messages):
            lines.append(f"- {item['role']}: {item['content'][:500]}")
    if memories:
        lines.append("当前会话已有工具事实：")
        for item in reversed(memories):
            facts = item["facts"]
            if not isinstance(facts, str):
                facts = json.dumps(facts, ensure_ascii=False)
            lines.append(f"- {item['memory_type']} ({item['tool_name']}): {facts[:800]}")
    return "\n".join(lines)


def _next_sequence(conn, conversation_id: str, user_id: int) -> int:
    row = conn.execute(
        """UPDATE chat_conversation
           SET next_sequence = next_sequence + 1
           WHERE id = %s AND user_id = %s
           RETURNING next_sequence - 1 AS sequence""",
        (conversation_id, user_id),
    ).fetchone()
    if not row:
        raise ValueError("会话不存在或无权访问")
    return row["sequence"]


def _touch_conversation(conn, conversation_id: str, title: str | None = None) -> None:
    if title:
        conn.execute(
            """UPDATE chat_conversation
               SET title = CASE WHEN title = '新会话' THEN %s ELSE title END,
                   updated_at = now()
               WHERE id = %s""",
            (title, conversation_id),
        )
    else:
        conn.execute("UPDATE chat_conversation SET updated_at = now() WHERE id = %s", (conversation_id,))
