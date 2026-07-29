import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from elasticsearch import Elasticsearch, helpers

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from quest_rag.core.config import ELASTICSEARCH_JOBS_INDEX, ELASTICSEARCH_URL
from quest_rag.rag.document_embedding import get_embedding


RAW_PATH = ROOT_DIR / "documents" / "gansu_jobs_raw.json"


def build_content(job: dict) -> str:
    parts = [
        f"岗位名称: {job.get('title', '')}",
        f"单位名称: {job.get('company', '')}",
        f"工作地点: {job.get('address', '')}",
        f"薪资待遇: {job.get('salary', '')}",
        f"所属行业: {job.get('industry', '')}",
        f"公司规模: {job.get('scale', '')}",
        f"岗位类别: {job.get('category', '')}",
        f"招聘人数: {job.get('headcount', '')}",
        f"经验要求: {job.get('experience', '')}",
        f"学历要求: {job.get('education', '')}",
        f"更新时间: {job.get('updated', '')}",
    ]
    return "\n".join(part for part in parts if part and not part.endswith(": "))


def stable_id(job: dict) -> str:
    key = "|".join(
        [
            job.get("title", ""),
            job.get("company", ""),
            job.get("address", ""),
            job.get("salary", ""),
            job.get("category", ""),
        ]
    )
    return "gansu_job_" + hashlib.sha1(key.encode("utf-8")).hexdigest()


def main():
    jobs = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    client = Elasticsearch(ELASTICSEARCH_URL)
    crawled_at = datetime.now().isoformat()

    actions = []
    for index, job in enumerate(jobs, start=1):
        content = build_content(job)
        doc = {
            "title": job.get("title"),
            "company": job.get("company"),
            "city": "",
            "district": "",
            "address": job.get("address"),
            "salary": job.get("salary"),
            "education": job.get("education"),
            "experience": job.get("experience"),
            "industry": job.get("industry"),
            "scale": job.get("scale"),
            "category": job.get("category"),
            "headcount": job.get("headcount"),
            "updated": job.get("updated"),
            "content": content,
            "raw_text": job.get("raw_text"),
            "url": job.get("source_url"),
            "source": job.get("source", "甘肃省公共就业服务网"),
            "source_page": job.get("page"),
            "crawled_at": crawled_at,
            "embedding": get_embedding(content),
        }
        actions.append(
            {
                "_op_type": "index",
                "_index": ELASTICSEARCH_JOBS_INDEX,
                "_id": stable_id(job),
                "_source": doc,
            }
        )

        if len(actions) >= 25:
            helpers.bulk(client, actions, refresh=False)
            print(f"indexed: {index}")
            actions.clear()

    if actions:
        helpers.bulk(client, actions, refresh=False)

    client.indices.refresh(index=ELASTICSEARCH_JOBS_INDEX)
    print(f"total_jobs: {len(jobs)}")
    print(f"index: {ELASTICSEARCH_JOBS_INDEX}")


if __name__ == "__main__":
    main()
