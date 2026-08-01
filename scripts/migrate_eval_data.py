"""将评测相关数据从旧 quest_rag 库迁移到新 vector_db 库。"""
import json
import psycopg
from psycopg.rows import dict_row

OLD_DB = "postgresql://postgres:difyai123456@192.168.1.43:5432/quest_rag"
NEW_DB = "postgresql://vector_user:vector_pass@192.168.1.43:5433/vector_db"

# 各表中的 JSONB 列
JSONB_COLS = {
    "evaluation_documents": ["raw_pages", "metadata"],
    "evaluation_datasets": ["items"],
    "evaluation_runs": ["document_scope", "clean_options", "split_options", "retrieval_options", "summary"],
    "evaluation_items": ["expected_source_ids", "expected_chunk_ids", "retrieval_queries", "retrieved", "metrics"],
}


def migrate():
    old = psycopg.connect(OLD_DB, connect_timeout=5, row_factory=dict_row)
    new = psycopg.connect(NEW_DB, connect_timeout=5, row_factory=dict_row)

    for table in ["evaluation_documents", "evaluation_datasets", "evaluation_runs", "evaluation_items"]:
        rows = old.execute(f"SELECT * FROM {table} ORDER BY created_at").fetchall()
        if not rows:
            print(f"  {table}: 0 rows (skip)")
            continue

        columns = list(rows[0].keys())
        jsonb_set = set(JSONB_COLS.get(table, []))
        cols_str = ", ".join(columns)

        for row in rows:
            values = {}
            for col in columns:
                val = row[col]
                if col in jsonb_set:
                    values[col] = json.dumps(val, ensure_ascii=False, default=str)
                else:
                    values[col] = val

            placeholders = ", ".join(f"%({col})s" for col in columns)
            new.execute(
                f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING",
                values,
            )

        print(f"  {table}: {len(rows)} rows migrated")

    new.commit()
    old.close()
    new.close()
    print("Done.")


if __name__ == "__main__":
    migrate()
