from quest_rag.rag.document_embedding import get_embedding
from quest_rag.rag.pg_store import keyword_search_jobs, vector_search_jobs


def search_jobs(query: str, top_k: int = 10) -> list[dict]:
    top_k = max(1, min(top_k, 10))
    query_vector = get_embedding(query)

    vector_hits = vector_search_jobs(query_vector, top_k * 2)
    keyword_hits = keyword_search_jobs(query, top_k * 2)
    return merge_job_results(vector_hits, keyword_hits, top_k)


def merge_job_results(vector_hits: list[dict], keyword_hits: list[dict], top_k: int) -> list[dict]:
    merged: dict[str, dict] = {}

    for item in vector_hits:
        job = _row_to_job(item, vector_score=item.get("similarity", 0), keyword_score=0)
        merged[job["id"]] = job

    for item in keyword_hits:
        if item["id"] not in merged:
            merged[item["id"]] = _row_to_job(item, vector_score=0, keyword_score=min(item.get("rank", 0) * 3, 5))
        else:
            merged[item["id"]]["keyword_score"] = min(item.get("rank", 0) * 3, 5)

    results = []
    for job in merged.values():
        job["score"] = job["keyword_score"] * 0.55 + job["vector_score"] * 0.45
        results.append(job)

    return sorted(
        results,
        key=lambda j: (j["keyword_score"] > 0, j["score"]),
        reverse=True,
    )[:top_k]


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
