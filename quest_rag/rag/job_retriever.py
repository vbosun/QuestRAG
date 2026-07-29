from elasticsearch import Elasticsearch

from quest_rag.core.config import ELASTICSEARCH_JOBS_INDEX, ELASTICSEARCH_URL
from quest_rag.rag.document_embedding import get_embedding


def search_jobs(query: str, top_k: int = 10) -> list[dict]:
    top_k = max(1, min(top_k, 10))
    query_vector = get_embedding(query)
    client = Elasticsearch(ELASTICSEARCH_URL)

    keyword_hits = keyword_search_jobs(client, query, top_k)
    vector_hits = vector_search_jobs(client, query_vector, top_k)
    return merge_job_results(keyword_hits, vector_hits, top_k)


def keyword_search_jobs(client: Elasticsearch, query: str, top_k: int) -> list[dict]:
    response = client.search(
        index=ELASTICSEARCH_JOBS_INDEX,
        size=top_k,
        query={
            "multi_match": {
                "query": query,
                "fields": [
                    "title^4",
                    "category^3",
                    "company^2",
                    "address^2",
                    "salary",
                    "education",
                    "experience",
                    "industry",
                    "content",
                ],
                "type": "best_fields",
            }
        },
    )
    max_score = response["hits"].get("max_score") or 1
    return [
        hit_to_job(hit, keyword_score=hit["_score"] / max_score, vector_score=0)
        for hit in response["hits"]["hits"]
    ]


def vector_search_jobs(client: Elasticsearch, query_vector: list[float], top_k: int) -> list[dict]:
    response = client.search(
        index=ELASTICSEARCH_JOBS_INDEX,
        size=top_k,
        query={
            "script_score": {
                "query": {"match_all": {}},
                "script": {
                    "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                    "params": {"query_vector": query_vector},
                },
            }
        },
    )
    return [
        hit_to_job(hit, keyword_score=0, vector_score=max(hit["_score"] - 1.0, 0))
        for hit in response["hits"]["hits"]
    ]


def merge_job_results(keyword_hits: list[dict], vector_hits: list[dict], top_k: int) -> list[dict]:
    merged: dict[str, dict] = {}
    for item in vector_hits:
        merged[item["id"]] = item

    for item in keyword_hits:
        if item["id"] not in merged:
            merged[item["id"]] = item
        else:
            merged[item["id"]]["keyword_score"] = item["keyword_score"]

    results = []
    for item in merged.values():
        item["score"] = item["keyword_score"] * 0.55 + item["vector_score"] * 0.45
        results.append(item)

    return sorted(
        results,
        key=lambda item: (item["keyword_score"] > 0, item["score"]),
        reverse=True,
    )[:top_k]


def hit_to_job(hit: dict, keyword_score: float, vector_score: float) -> dict:
    source = hit["_source"]
    return {
        "id": hit["_id"],
        "title": source.get("title"),
        "company": source.get("company"),
        "address": source.get("address"),
        "salary": source.get("salary"),
        "education": source.get("education"),
        "experience": source.get("experience"),
        "industry": source.get("industry"),
        "scale": source.get("scale"),
        "category": source.get("category"),
        "headcount": source.get("headcount"),
        "updated": source.get("updated"),
        "source": source.get("source"),
        "url": source.get("url"),
        "score": 0,
        "keyword_score": keyword_score,
        "vector_score": vector_score,
    }
