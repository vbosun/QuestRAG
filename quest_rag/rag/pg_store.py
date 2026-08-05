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
                text_length INTEGER DEFAULT 0,
                token_count INTEGER DEFAULT 0,
                format TEXT,
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
                retrieval_index_name TEXT,
                evaluation_mode TEXT NOT NULL DEFAULT 'retrieval',
                document_scope JSONB NOT NULL DEFAULT '{}'::jsonb,
                clean_options JSONB NOT NULL DEFAULT '{}'::jsonb,
                split_options JSONB NOT NULL DEFAULT '{}'::jsonb,
                retrieval_options JSONB NOT NULL DEFAULT '{}'::jsonb,
                generation_options JSONB NOT NULL DEFAULT '{}'::jsonb,
                ragas_options JSONB NOT NULL DEFAULT '{}'::jsonb,
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
                required_points JSONB NOT NULL DEFAULT '[]'::jsonb,
                forbidden_claims JSONB NOT NULL DEFAULT '[]'::jsonb,
                answer_type TEXT,
                expected_citation_required BOOLEAN NOT NULL DEFAULT false,
                expected_source_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                expected_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                expected_chunk_text TEXT,
                should_refuse BOOLEAN NOT NULL DEFAULT false,
                refusal_reason TEXT,
                retrieval_queries JSONB NOT NULL DEFAULT '[]'::jsonb,
                retrieved JSONB NOT NULL DEFAULT '[]'::jsonb,
                metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
                generated_answer TEXT,
                answer_citations JSONB NOT NULL DEFAULT '[]'::jsonb,
                tool_calls JSONB NOT NULL DEFAULT '[]'::jsonb,
                generation_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
                ragas_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
                generation_error TEXT,
                latency_ms INTEGER,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute("ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS retrieval_index_name TEXT")
        conn.execute("ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS evaluation_mode TEXT NOT NULL DEFAULT 'retrieval'")
        conn.execute("ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS generation_options JSONB NOT NULL DEFAULT '{}'::jsonb")
        conn.execute("ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS ragas_options JSONB NOT NULL DEFAULT '{}'::jsonb")
        conn.execute("ALTER TABLE evaluation_items ADD COLUMN IF NOT EXISTS should_refuse BOOLEAN NOT NULL DEFAULT false")
        conn.execute("ALTER TABLE evaluation_items ADD COLUMN IF NOT EXISTS retrieval_queries JSONB NOT NULL DEFAULT '[]'::jsonb")
        conn.execute("ALTER TABLE evaluation_items ADD COLUMN IF NOT EXISTS required_points JSONB NOT NULL DEFAULT '[]'::jsonb")
        conn.execute("ALTER TABLE evaluation_items ADD COLUMN IF NOT EXISTS forbidden_claims JSONB NOT NULL DEFAULT '[]'::jsonb")
        conn.execute("ALTER TABLE evaluation_items ADD COLUMN IF NOT EXISTS answer_type TEXT")
        conn.execute("ALTER TABLE evaluation_items ADD COLUMN IF NOT EXISTS expected_citation_required BOOLEAN NOT NULL DEFAULT false")
        conn.execute("ALTER TABLE evaluation_items ADD COLUMN IF NOT EXISTS refusal_reason TEXT")
        conn.execute("ALTER TABLE evaluation_items ADD COLUMN IF NOT EXISTS generated_answer TEXT")
        conn.execute("ALTER TABLE evaluation_items ADD COLUMN IF NOT EXISTS answer_citations JSONB NOT NULL DEFAULT '[]'::jsonb")
        conn.execute("ALTER TABLE evaluation_items ADD COLUMN IF NOT EXISTS tool_calls JSONB NOT NULL DEFAULT '[]'::jsonb")
        conn.execute("ALTER TABLE evaluation_items ADD COLUMN IF NOT EXISTS generation_metrics JSONB NOT NULL DEFAULT '{}'::jsonb")
        conn.execute("ALTER TABLE evaluation_items ADD COLUMN IF NOT EXISTS ragas_metrics JSONB NOT NULL DEFAULT '{}'::jsonb")
        conn.execute("ALTER TABLE evaluation_items ADD COLUMN IF NOT EXISTS generation_error TEXT")
        conn.execute("ALTER TABLE evaluation_items ADD COLUMN IF NOT EXISTS latency_ms INTEGER")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS system_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            INSERT INTO system_config (key, value, description)
            VALUES ('retrieval', %s, '正式环境检索参数，JSON 格式：top_k/recall_k/mode/rrf_k')
            ON CONFLICT (key) DO NOTHING
            """,
            (json_dumps({"top_k": 5, "recall_k": 15, "mode": "hybrid", "rrf_k": 60}),),
        )


def upsert_document(
    *,
    doc_id: str,
    filename: str,
    title: str,
    raw_text: str,
    raw_pages: list[dict],
    metadata: dict,
    content_hash: str | None = None,
    text_length: int = 0,
    token_count: int = 0,
    fmt: str | None = None,
):
    version_id = f"{doc_id}::v::{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO documents (id, filename, title, metadata, content_hash, text_length, token_count, format, updated_at)
            VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, now())
            ON CONFLICT (id) DO UPDATE SET
                filename = EXCLUDED.filename,
                title = EXCLUDED.title,
                metadata = EXCLUDED.metadata,
                content_hash = EXCLUDED.content_hash,
                text_length = EXCLUDED.text_length,
                token_count = EXCLUDED.token_count,
                format = EXCLUDED.format,
                updated_at = now()
            """,
            (doc_id, filename, title, json.dumps(metadata, ensure_ascii=False), content_hash, text_length, token_count, fmt),
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
                id, name, status, dataset_path, es_index_name, retrieval_index_name,
                evaluation_mode, document_scope, clean_options, split_options, retrieval_options,
                generation_options, ragas_options, summary, error
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s)
            """,
            (
                record["id"],
                record["name"],
                record["status"],
                record["dataset_path"],
                record["es_index_name"],
                record.get("retrieval_index_name") or record["es_index_name"],
                record.get("evaluation_mode", "retrieval"),
                json_dumps(record.get("document_scope", {})),
                json_dumps(record.get("clean_options", {})),
                json_dumps(record.get("split_options", {})),
                json_dumps(record.get("retrieval_options", {})),
                json_dumps(record.get("generation_options", {})),
                json_dumps(record.get("ragas_options", {})),
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
                    required_points, forbidden_claims, answer_type, expected_citation_required,
                    expected_source_ids, expected_chunk_ids, expected_chunk_text,
                    should_refuse, refusal_reason, retrieval_queries, retrieved, metrics,
                    generated_answer, answer_citations, tool_calls, generation_metrics,
                    ragas_metrics, generation_error, latency_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s)
                """,
                (
                    item["id"],
                    item["run_id"],
                    item.get("question_id"),
                    item["question"],
                    item.get("expected_answer"),
                    json_dumps(item.get("required_points", [])),
                    json_dumps(item.get("forbidden_claims", [])),
                    item.get("answer_type"),
                    item.get("expected_citation_required", False),
                    json_dumps(item.get("expected_source_ids", [])),
                    json_dumps(item.get("expected_chunk_ids", [])),
                    item.get("expected_chunk_text"),
                    item.get("should_refuse", False),
                    item.get("refusal_reason"),
                    json_dumps(item.get("retrieval_queries", [])),
                    json_dumps(item.get("retrieved", [])),
                    json_dumps(item.get("metrics", {})),
                    item.get("generated_answer"),
                    json_dumps(item.get("answer_citations", [])),
                    json_dumps(item.get("tool_calls", [])),
                    json_dumps(item.get("generation_metrics", {})),
                    json_dumps(item.get("ragas_metrics", {})),
                    item.get("generation_error"),
                    item.get("latency_ms"),
                ),
            )


def list_evaluation_runs() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, name, status, dataset_path, es_index_name,
                   COALESCE(retrieval_index_name, es_index_name) AS retrieval_index_name,
                   evaluation_mode, document_scope,
                   clean_options, split_options, retrieval_options,
                   generation_options, ragas_options, summary,
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
            SELECT id, name, status, dataset_path, es_index_name,
                   COALESCE(retrieval_index_name, es_index_name) AS retrieval_index_name,
                   evaluation_mode, document_scope,
                   clean_options, split_options, retrieval_options,
                   generation_options, ragas_options, summary,
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
                    required_points, forbidden_claims, answer_type, expected_citation_required,
                    expected_source_ids, expected_chunk_ids, expected_chunk_text,
                    should_refuse, refusal_reason, retrieval_queries, retrieved, metrics,
                    generated_answer, answer_citations, tool_calls, generation_metrics,
                    ragas_metrics, generation_error, latency_ms, created_at
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


def get_system_config(key: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT key, value, description, updated_at FROM system_config WHERE key = %s",
            (key,),
        ).fetchone()
    if not row:
        return None
    result = dict(row)
    try:
        result["value"] = json.loads(result["value"])
    except (json.JSONDecodeError, TypeError):
        pass
    return result


def set_system_config(key: str, value: Any, description: str = "") -> dict:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO system_config (key, value, description, updated_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                description = EXCLUDED.description,
                updated_at = now()
            """,
            (key, json_dumps(value), description),
        )
    return get_system_config(key)


def list_system_configs() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT key, value, description, updated_at FROM system_config ORDER BY key"
        ).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        try:
            item["value"] = json.loads(item["value"])
        except (json.JSONDecodeError, TypeError):
            pass
        results.append(item)
    return results


# ── Jobs (pgvector) ──────────────────────────────────────────

_JOBS_TABLE_INITIALIZED = False


def init_jobs_table():
    global _JOBS_TABLE_INITIALIZED
    if _JOBS_TABLE_INITIALIZED:
        return
    with get_conn() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT,
                company TEXT,
                address TEXT,
                salary TEXT,
                education TEXT,
                experience TEXT,
                industry TEXT,
                scale TEXT,
                category TEXT,
                headcount TEXT,
                updated TEXT,
                source TEXT,
                url TEXT,
                content TEXT,
                embedding vector(1024),
                tsv TSVECTOR GENERATED ALWAYS AS (
                    to_tsvector('chinese',
                        coalesce(title, '') || ' ' ||
                        coalesce(content, '') || ' ' ||
                        coalesce(company, '') || ' ' ||
                        coalesce(category, '') || ' ' ||
                        coalesce(address, '')
                    )
                ) STORED,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_jobs_embedding
            ON jobs USING hnsw (embedding vector_cosine_ops)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_jobs_tsv
            ON jobs USING GIN(tsv)
            """
        )
    _JOBS_TABLE_INITIALIZED = True


def insert_jobs_batch(rows: list[dict]):
    if not rows:
        return
    init_jobs_table()
    with get_conn() as conn:
        with conn.cursor() as cur:
            for row in rows:
                emb = row.get("embedding")
                emb_literal = _vec_to_pg_vector(emb) if emb else "NULL"
                cur.execute(
                    f"""
                    INSERT INTO jobs (id, title, company, address, salary, education,
                                      experience, industry, scale, category, headcount,
                                      updated, source, url, content, embedding)
                    VALUES (%(id)s, %(title)s, %(company)s, %(address)s, %(salary)s,
                            %(education)s, %(experience)s, %(industry)s, %(scale)s,
                            %(category)s, %(headcount)s, %(updated)s, %(source)s,
                            %(url)s, %(content)s, {emb_literal}::vector)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        company = EXCLUDED.company,
                        address = EXCLUDED.address,
                        salary = EXCLUDED.salary,
                        education = EXCLUDED.education,
                        experience = EXCLUDED.experience,
                        industry = EXCLUDED.industry,
                        scale = EXCLUDED.scale,
                        category = EXCLUDED.category,
                        headcount = EXCLUDED.headcount,
                        updated = EXCLUDED.updated,
                        source = EXCLUDED.source,
                        url = EXCLUDED.url,
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding
                    """,
                    {k: v for k, v in row.items() if k != "embedding"},
                )


def delete_all_jobs():
    with get_conn() as conn:
        conn.execute("DELETE FROM jobs")


def vector_search_jobs(query_vector: list[float], top_k: int) -> list[dict]:
    """pgvector HNSW 索引检索。"""
    init_jobs_table()
    vec_str = f"[{','.join(str(v) for v in query_vector)}]"
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *, 1.0 - (embedding <=> %s::vector) AS similarity
            FROM jobs
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (vec_str, vec_str, top_k),
        ).fetchall()
    return [dict(row) for row in rows]


def keyword_search_jobs(query: str, top_k: int) -> list[dict]:
    init_jobs_table()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *, ts_rank(tsv, query) AS rank
            FROM jobs, plainto_tsquery('chinese', %s) query
            WHERE tsv @@ query
            ORDER BY rank DESC
            LIMIT %s
            """,
            (query, top_k),
        ).fetchall()
    return [dict(row) for row in rows]


def _vec_to_pg_vector(vec: list[float]) -> str:
    return "[" + ",".join(str(v) for v in vec) + "]"


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
