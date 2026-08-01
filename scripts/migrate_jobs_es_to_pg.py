"""一次性迁移脚本：将 Elasticsearch 中的岗位数据迁移到 PostgreSQL (pgvector)。"""
from elasticsearch import Elasticsearch

from quest_rag.core.config import ELASTICSEARCH_JOBS_INDEX, ELASTICSEARCH_URL
from quest_rag.rag.pg_store import delete_all_jobs, init_jobs_table, insert_jobs_batch

BATCH_SIZE = 500


def migrate():
    es = Elasticsearch(ELASTICSEARCH_URL)

    # 检查 ES 索引是否存在
    if not es.indices.exists(index=ELASTICSEARCH_JOBS_INDEX):
        print(f"ES 索引 {ELASTICSEARCH_JOBS_INDEX} 不存在，跳过迁移。")
        return

    count_resp = es.count(index=ELASTICSEARCH_JOBS_INDEX)
    total = count_resp["count"]
    print(f"ES 岗位总数: {total}")
    if total == 0:
        print("ES 中无岗位数据，跳过迁移。")
        return

    # 初始化 PG 表
    init_jobs_table()

    # 清空旧数据（幂等迁移）
    delete_all_jobs()
    print("已清空 PG jobs 表。")

    # 滚动读取 ES 数据
    resp = es.search(
        index=ELASTICSEARCH_JOBS_INDEX,
        query={"match_all": {}},
        size=BATCH_SIZE,
        scroll="2m",
        _source_excludes=[],
    )
    scroll_id = resp["_scroll_id"]
    hits = resp["hits"]["hits"]

    migrated = 0
    while hits:
        rows = []
        for hit in hits:
            src = hit["_source"]
            embedding = src.get("embedding")
            rows.append(
                {
                    "id": hit["_id"],
                    "title": src.get("title"),
                    "company": src.get("company"),
                    "address": src.get("address"),
                    "salary": src.get("salary"),
                    "education": src.get("education"),
                    "experience": src.get("experience"),
                    "industry": src.get("industry"),
                    "scale": src.get("scale"),
                    "category": src.get("category"),
                    "headcount": src.get("headcount"),
                    "updated": src.get("updated"),
                    "source": src.get("source"),
                    "url": src.get("url"),
                    "content": src.get("content"),
                    "embedding": embedding if embedding else None,
                }
            )
        insert_jobs_batch(rows)
        migrated += len(rows)
        print(f"已迁移 {migrated}/{total} 条...")

        resp = es.scroll(scroll_id=scroll_id, scroll="2m")
        hits = resp["hits"]["hits"]
        scroll_id = resp.get("_scroll_id", scroll_id)

    es.clear_scroll(scroll_id=scroll_id)
    print(f"迁移完成，共导入 {migrated} 条岗位数据。")


if __name__ == "__main__":
    migrate()
