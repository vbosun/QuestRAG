from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from typing import Any

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


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                title TEXT NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                content_hash TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_versions (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                raw_text TEXT NOT NULL,
                raw_pages JSONB NOT NULL DEFAULT '[]'::jsonb,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_runs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                dataset_path TEXT NOT NULL,
                es_index_name TEXT NOT NULL,
                document_scope JSONB NOT NULL DEFAULT '{}'::jsonb,
                clean_options JSONB NOT NULL DEFAULT '{}'::jsonb,
                split_options JSONB NOT NULL DEFAULT '{}'::jsonb,
                retrieval_options JSONB NOT NULL DEFAULT '{}'::jsonb,
                summary JSONB NOT NULL DEFAULT '{}'::jsonb,
                error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                completed_at TIMESTAMPTZ
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                title TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_size INTEGER NOT NULL DEFAULT 0,
                raw_text TEXT NOT NULL,
                raw_pages JSONB NOT NULL DEFAULT '[]'::jsonb,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_datasets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                items JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_items (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
                question_id TEXT,
                question TEXT NOT NULL,
                expected_answer TEXT,
                expected_source_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                expected_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                expected_chunk_text TEXT,
                should_refuse BOOLEAN NOT NULL DEFAULT false,
                retrieval_queries JSONB NOT NULL DEFAULT '[]'::jsonb,
                retrieved JSONB NOT NULL DEFAULT '[]'::jsonb,
                metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute("ALTER TABLE evaluation_items ADD COLUMN IF NOT EXISTS should_refuse BOOLEAN NOT NULL DEFAULT false")
        conn.execute("ALTER TABLE evaluation_items ADD COLUMN IF NOT EXISTS retrieval_queries JSONB NOT NULL DEFAULT '[]'::jsonb")


def upsert_document(
    *,
    doc_id: str,
    filename: str,
    title: str,
    raw_text: str,
    raw_pages: list[dict],
    metadata: dict,
    content_hash: str | None = None,
):
    version_id = f"{doc_id}::v::{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO documents (id, filename, title, metadata, content_hash, updated_at)
            VALUES (%s, %s, %s, %s::jsonb, %s, now())
            ON CONFLICT (id) DO UPDATE SET
                filename = EXCLUDED.filename,
                title = EXCLUDED.title,
                metadata = EXCLUDED.metadata,
                content_hash = EXCLUDED.content_hash,
                updated_at = now()
            """,
            (doc_id, filename, title, json.dumps(metadata, ensure_ascii=False), content_hash),
        )
        conn.execute(
            """
            INSERT INTO document_versions (id, document_id, raw_text, raw_pages, metadata)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
            """,
            (
                version_id,
                doc_id,
                raw_text,
                json.dumps(raw_pages, ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False),
            ),
        )


def get_document_stats() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.filename,
                   COALESCE(LENGTH(v.raw_text), 0) AS text_length
            FROM documents d
            JOIN LATERAL (
                SELECT raw_text FROM document_versions
                WHERE document_id = d.id
                ORDER BY created_at DESC
                LIMIT 1
            ) v ON true
            """
        ).fetchall()
    return [dict(row) for row in rows]


def delete_document(doc_id: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM documents WHERE id = %s", (doc_id,))


def get_latest_document_version(doc_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT d.id AS document_id, d.filename, d.title, d.metadata AS document_metadata,
                   v.raw_text, v.raw_pages, v.metadata AS version_metadata, v.created_at
            FROM documents d
            JOIN document_versions v ON v.document_id = d.id
            WHERE d.id = %s
            ORDER BY v.created_at DESC
            LIMIT 1
            """,
            (doc_id,),
        ).fetchone()
    return dict(row) if row else None


def create_evaluation_run(record: dict):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO evaluation_runs (
                id, name, status, dataset_path, es_index_name, document_scope,
                clean_options, split_options, retrieval_options, summary, error
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s)
            """,
            (
                record["id"],
                record["name"],
                record["status"],
                record["dataset_path"],
                record["es_index_name"],
                json_dumps(record.get("document_scope", {})),
                json_dumps(record.get("clean_options", {})),
                json_dumps(record.get("split_options", {})),
                json_dumps(record.get("retrieval_options", {})),
                json_dumps(record.get("summary", {})),
                record.get("error"),
            ),
        )


def finish_evaluation_run(run_id: str, *, status: str, summary: dict, error: str | None = None):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE evaluation_runs
            SET status = %s, summary = %s::jsonb, error = %s, completed_at = now()
            WHERE id = %s
            """,
            (status, json_dumps(summary), error, run_id),
        )


def add_evaluation_items(items: list[dict]):
    if not items:
        return
    with get_conn() as conn:
        for item in items:
            conn.execute(
                """
                INSERT INTO evaluation_items (
                    id, run_id, question_id, question, expected_answer,
                    expected_source_ids, expected_chunk_ids, expected_chunk_text,
                    should_refuse, retrieval_queries, retrieved, metrics
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                """,
                (
                    item["id"],
                    item["run_id"],
                    item.get("question_id"),
                    item["question"],
                    item.get("expected_answer"),
                    json_dumps(item.get("expected_source_ids", [])),
                    json_dumps(item.get("expected_chunk_ids", [])),
                    item.get("expected_chunk_text"),
                    item.get("should_refuse", False),
                    json_dumps(item.get("retrieval_queries", [])),
                    json_dumps(item.get("retrieved", [])),
                    json_dumps(item.get("metrics", {})),
                ),
            )


def list_evaluation_runs() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, name, status, dataset_path, es_index_name, document_scope,
                   clean_options, split_options, retrieval_options, summary,
                   error, created_at, completed_at
            FROM evaluation_runs
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_evaluation_run(run_id: str) -> dict | None:
    with get_conn() as conn:
        run = conn.execute(
            """
            SELECT id, name, status, dataset_path, es_index_name, document_scope,
                   clean_options, split_options, retrieval_options, summary,
                   error, created_at, completed_at
            FROM evaluation_runs
            WHERE id = %s
            """,
            (run_id,),
        ).fetchone()
        if not run:
            return None
        items = conn.execute(
            """
             SELECT id, run_id, question_id, question, expected_answer,
                    expected_source_ids, expected_chunk_ids, expected_chunk_text,
                    should_refuse, retrieval_queries, retrieved, metrics, created_at
             FROM evaluation_items
            WHERE run_id = %s
            ORDER BY question_id NULLS LAST, created_at ASC
            """,
            (run_id,),
        ).fetchall()
    result = dict(run)
    result["items"] = [dict(item) for item in items]
    return result


def delete_evaluation_run(run_id: str) -> dict | None:
    run = get_evaluation_run(run_id)
    if not run:
        return None
    with get_conn() as conn:
        conn.execute("DELETE FROM evaluation_runs WHERE id = %s", (run_id,))
    return run


def upsert_evaluation_document(record: dict):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO evaluation_documents (
                id, filename, title, file_type, file_size, raw_text, raw_pages, metadata, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, now())
            ON CONFLICT (id) DO UPDATE SET
                filename = EXCLUDED.filename,
                title = EXCLUDED.title,
                file_type = EXCLUDED.file_type,
                file_size = EXCLUDED.file_size,
                raw_text = EXCLUDED.raw_text,
                raw_pages = EXCLUDED.raw_pages,
                metadata = EXCLUDED.metadata,
                updated_at = now()
            """,
            (
                record["id"],
                record["filename"],
                record["title"],
                record["file_type"],
                record["file_size"],
                record["raw_text"],
                json_dumps(record.get("raw_pages", [])),
                json_dumps(record.get("metadata", {})),
            ),
        )


def list_evaluation_documents() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, filename, title, file_type, file_size, metadata, created_at, updated_at
            FROM evaluation_documents
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_evaluation_document(doc_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, filename, title, file_type, file_size, raw_text, raw_pages, metadata, created_at, updated_at
            FROM evaluation_documents
            WHERE id = %s
            """,
            (doc_id,),
        ).fetchone()
    return dict(row) if row else None


def delete_evaluation_document(doc_id: str) -> bool:
    with get_conn() as conn:
        result = conn.execute("DELETE FROM evaluation_documents WHERE id = %s", (doc_id,))
    return result.rowcount > 0


def upsert_evaluation_dataset(record: dict):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO evaluation_datasets (id, name, items, updated_at)
            VALUES (%s, %s, %s::jsonb, now())
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                items = EXCLUDED.items,
                updated_at = now()
            """,
            (record["id"], record["name"], json_dumps(record.get("items", []))),
        )


def list_evaluation_datasets() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, name, jsonb_array_length(items) AS item_count, created_at, updated_at
            FROM evaluation_datasets
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_evaluation_dataset(dataset_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, name, items, created_at, updated_at
            FROM evaluation_datasets
            WHERE id = %s
            """,
            (dataset_id,),
        ).fetchone()
    return dict(row) if row else None


def delete_evaluation_dataset(dataset_id: str) -> bool:
    with get_conn() as conn:
        result = conn.execute("DELETE FROM evaluation_datasets WHERE id = %s", (dataset_id,))
    return result.rowcount > 0


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
