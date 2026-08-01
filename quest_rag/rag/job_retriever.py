from quest_rag.rag.document_embedding import get_embedding
from quest_rag.rag.pg_store import keyword_search_jobs, vector_search_jobs


def search_jobs(query: str, top_k: int = 10) -> list[dict]:
    top_k = max(1, min(top_k, 10))
    query_vector = get_embedding(query)

    vector_hits = vector_search_jobs(query_vector, top_k * 2)
    keyword_hits = keyword_search_jobs(query, top_k * 2)
    return merge_job_results(vector_hits, keyword_hits, top_k)


def merge_job_results(vector_hits: list[dict], keyword_hits: list[dict], top_k: int, rrf_k: int = 60) -> list[dict]:
    """RRF 倒数排名融合——只看排名不看分数，绕开分数量纲不可比问题。"""
    rrf_scores: dict[str, float] = {}
    job_map: dict[str, dict] = {}

    for rank, item in enumerate(vector_hits, start=1):
        jid = item["id"]
        rrf_scores[jid] = rrf_scores.get(jid, 0) + 1.0 / (rrf_k + rank)
        if jid not in job_map:
            job_map[jid] = _row_to_job(item, vector_score=item.get("similarity", 0), keyword_score=0)

    for rank, item in enumerate(keyword_hits, start=1):
        jid = item["id"]
        rrf_scores[jid] = rrf_scores.get(jid, 0) + 1.0 / (rrf_k + rank)
        if jid not in job_map:
            job_map[jid] = _row_to_job(item, vector_score=0, keyword_score=3.0)
        else:
            job_map[jid]["keyword_score"] = 3.0

    sorted_ids = sorted(rrf_scores, key=lambda i: rrf_scores[i], reverse=True)

    results = []
    for jid in sorted_ids[:top_k]:
        job = job_map[jid]
        job["score"] = round(rrf_scores[jid], 6)
        results.append(job)

    return results


def _row_to_job(row: dict, vector_score: float, keyword_score: float) -> dict:
    return {
        "id": row["id"],
        "title": row.get("title"),
        "company": row.get("company"),
        "address": row.get("address"),
        "salary": row.get("salary"),
        "education": row.get("education"),
        "experience": row.get("experience"),
        "industry": row.get("industry"),
        "scale": row.get("scale"),
        "category": row.get("category"),
        "headcount": row.get("headcount"),
        "updated": row.get("updated"),
        "source": row.get("source"),
        "url": row.get("url"),
        "content": row.get("content"),
        "score": 0,
        "keyword_score": keyword_score,
        "vector_score": vector_score,
    }
