import sys
from pathlib import Path

from elasticsearch import Elasticsearch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from quest_rag.core.config import (
    ELASTICSEARCH_INDEX,
    ELASTICSEARCH_JOBS_INDEX,
    ELASTICSEARCH_URL,
)
from quest_rag.rag.document_embedding import get_embedding


def dense_vector_mapping(dims: int) -> dict:
    return {
        "type": "dense_vector",
        "dims": dims,
        "index": True,
        "similarity": "cosine",
    }


def create_index_if_missing(client: Elasticsearch, index_name: str, mappings: dict):
    if client.indices.exists(index=index_name):
        print(f"exists: {index_name}")
        return
    client.indices.create(index=index_name, mappings=mappings)
    print(f"created: {index_name}")


def main():
    client = Elasticsearch(ELASTICSEARCH_URL)
    dims = len(get_embedding("初始化 Elasticsearch 向量维度"))

    create_index_if_missing(
        client,
        ELASTICSEARCH_INDEX,
        {
            "properties": {
                "text": {"type": "text", "analyzer": "standard"},
                "embedding": dense_vector_mapping(dims),
                "metadata": {
                    "properties": {
                        "chunk_id": {"type": "keyword"},
                        "doc_id": {"type": "keyword"},
                        "filename": {"type": "keyword"},
                        "source": {"type": "keyword"},
                        "source_type": {"type": "keyword"},
                        "chunk_index": {"type": "integer"},
                        "start_index": {"type": "integer"},
                        "end_index": {"type": "integer"},
                    }
                },
            }
        },
    )

    create_index_if_missing(
        client,
        ELASTICSEARCH_JOBS_INDEX,
        {
            "properties": {
                "title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "company": {"type": "keyword"},
                "city": {"type": "keyword"},
                "district": {"type": "keyword"},
                "salary": {"type": "keyword"},
                "education": {"type": "keyword"},
                "experience": {"type": "keyword"},
                "content": {"type": "text", "analyzer": "standard"},
                "url": {"type": "keyword"},
                "source": {"type": "keyword"},
                "posted_at": {"type": "date", "ignore_malformed": True},
                "crawled_at": {"type": "date", "ignore_malformed": True},
                "embedding": dense_vector_mapping(dims),
            }
        },
    )

    print(f"embedding_dims: {dims}")
    print(f"elasticsearch_url: {ELASTICSEARCH_URL}")


if __name__ == "__main__":
    main()
