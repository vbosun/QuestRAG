import math
import re
from abc import ABC, abstractmethod
from datetime import datetime
from uuid import uuid4

from langchain_core.documents import Document

from quest_rag.core.config import (
    ELASTICSEARCH_INDEX,
    ELASTICSEARCH_URL,
    VECTOR_BACKEND,
)


vector_store: list[dict] = []


class VectorBackend(ABC):
    @abstractmethod
    def add_documents(self, docs: list[Document], embeddings: list[list[float]]) -> list[str]:
        pass

    @abstractmethod
    def delete_documents(self, doc_id: str):
        pass

    @abstractmethod
    def search(self, query: str, query_vector: list[float], top_k: int) -> list[dict]:
        pass

    @abstractmethod
    def list_documents(self) -> list[dict]:
        pass

    @abstractmethod
    def list_chunks(self, doc_id: str) -> list[dict]:
        pass


class MemoryVectorBackend(VectorBackend):
    def add_documents(self, docs: list[Document], embeddings: list[list[float]]) -> list[str]:
        ids = []
        for doc, embedding in zip(docs, embeddings, strict=True):
            chunk_id = f"chunk_{uuid4().hex}"
            metadata = doc.metadata.copy()
            metadata["chunk_id"] = chunk_id
            vector_store.append(
                {
                    "id": chunk_id,
                    "text": doc.page_content,
                    "embedding": embedding,
                    "metadata": metadata,
                }
            )
            ids.append(chunk_id)
        return ids

    def delete_documents(self, doc_id: str):
        vector_store[:] = [
            chunk
            for chunk in vector_store
            if chunk["metadata"].get("doc_id") != doc_id
        ]

    def search(self, query: str, query_vector: list[float], top_k: int) -> list[dict]:
        vector_results = vector_search(query_vector, vector_store, top_k)
        keyword_results = keyword_search(query, vector_store, top_k)
        return merge_results(vector_results, keyword_results, top_k)

    def list_documents(self) -> list[dict]:
        docs: dict[str, dict] = {}
        for chunk in vector_store:
            metadata = chunk.get("metadata", {})
            doc_id = metadata.get("doc_id")
            if not doc_id:
                continue
            item = docs.setdefault(
                doc_id,
                {
                    "doc_id": doc_id,
                    "filename": metadata.get("filename") or doc_id,
                    "chunk_count": 0,
                    "uploaded_at": metadata.get("ingested_at") or datetime.now().isoformat(),
                },
            )
            item["chunk_count"] += 1
        return list(docs.values())

    def list_chunks(self, doc_id: str) -> list[dict]:
        chunks = [
            {
                "chunk_id": chunk["id"],
                "text": chunk["text"],
                "metadata": chunk.get("metadata", {}),
                "length": len(chunk.get("text", "")),
            }
            for chunk in vector_store
            if chunk.get("metadata", {}).get("doc_id") == doc_id
        ]
        return sorted(chunks, key=lambda item: item["metadata"].get("chunk_index", 0))


class ElasticsearchVectorBackend(VectorBackend):
    def __init__(self, url: str, index_name: str):
        try:
            from elasticsearch import Elasticsearch
        except ImportError as exc:
            raise RuntimeError(
                "已配置 VECTOR_BACKEND=elasticsearch，但缺少 elasticsearch 依赖。"
            ) from exc

        self.client = Elasticsearch(url)
        self.index_name = index_name

    def add_documents(self, docs: list[Document], embeddings: list[list[float]]) -> list[str]:
        if not docs:
            return []

        self._ensure_index(len(embeddings[0]))
        ids = []
        for doc, embedding in zip(docs, embeddings, strict=True):
            chunk_id = f"chunk_{uuid4().hex}"
            metadata = doc.metadata.copy()
            metadata["chunk_id"] = chunk_id
            self.client.index(
                index=self.index_name,
                id=chunk_id,
                document={
                    "text": doc.page_content,
                    "embedding": embedding,
                    "metadata": metadata,
                },
                refresh=True,
            )
            ids.append(chunk_id)
        return ids

    def delete_documents(self, doc_id: str):
        self.client.delete_by_query(
            index=self.index_name,
            query={"term": {"metadata.doc_id": doc_id}},
            refresh=True,
            conflicts="proceed",
            ignore_unavailable=True,
        )

    def search(self, query: str, query_vector: list[float], top_k: int) -> list[dict]:
        vector_results = self._vector_search(query_vector, top_k)
        keyword_results = self._keyword_search(query, top_k)
        return merge_results(vector_results, keyword_results, top_k)

    def list_documents(self) -> list[dict]:
        response = self.client.search(
            index=self.index_name,
            size=0,
            query={"exists": {"field": "metadata.doc_id"}},
            aggs={
                "documents": {
                    "terms": {
                        "field": "metadata.doc_id",
                        "size": 1000,
                        "order": {"_key": "asc"},
                    },
                    "aggs": {
                        "sample": {
                            "top_hits": {
                                "size": 1,
                                "_source": {
                                    "includes": [
                                        "metadata.doc_id",
                                        "metadata.filename",
                                        "metadata.source",
                                        "metadata.ingested_at",
                                        "metadata.creationdate",
                                    ]
                                },
                            }
                        }
                    },
                }
            },
        )
        docs = []
        buckets = response.get("aggregations", {}).get("documents", {}).get("buckets", [])
        for bucket in buckets:
            hit = bucket["sample"]["hits"]["hits"][0]
            metadata = hit["_source"].get("metadata", {})
            docs.append(
                {
                    "doc_id": bucket["key"],
                    "filename": metadata.get("filename") or metadata.get("source") or bucket["key"],
                    "chunk_count": bucket["doc_count"],
                    "uploaded_at": metadata.get("ingested_at")
                    or metadata.get("creationdate")
                    or datetime.now().isoformat(),
                }
            )
        return docs

    def list_chunks(self, doc_id: str) -> list[dict]:
        response = self.client.search(
            index=self.index_name,
            size=1000,
            query={"term": {"metadata.doc_id": doc_id}},
            sort=[
                {"metadata.chunk_index": {"order": "asc", "missing": "_last"}},
            ],
            _source=["text", "metadata"],
        )
        return [
            {
                "chunk_id": hit["_id"],
                "text": hit["_source"].get("text", ""),
                "metadata": hit["_source"].get("metadata", {}),
                "length": len(hit["_source"].get("text", "")),
            }
            for hit in response["hits"]["hits"]
        ]

    def _ensure_index(self, dims: int):
        if self.client.indices.exists(index=self.index_name):
            return
        self.client.indices.create(
            index=self.index_name,
            mappings={
                "properties": {
                    "text": {"type": "text", "analyzer": "standard"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": dims,
                        "index": True,
                        "similarity": "cosine",
                    },
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

    def _vector_search(self, query_vector: list[float], top_k: int) -> list[dict]:
        response = self.client.search(
            index=self.index_name,
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
            self._hit_to_chunk(hit, vector_score=max(hit["_score"] - 1.0, 0), keyword_score=0)
            for hit in response["hits"]["hits"]
        ]

    def _keyword_search(self, query: str, top_k: int) -> list[dict]:
        if not query:
            return []
        response = self.client.search(
            index=self.index_name,
            size=top_k,
            query={"match": {"text": query}},
        )
        max_score = response["hits"].get("max_score") or 1
        return [
            self._hit_to_chunk(hit, vector_score=0, keyword_score=hit["_score"] / max_score)
            for hit in response["hits"]["hits"]
        ]

    def _hit_to_chunk(self, hit: dict, vector_score: float, keyword_score: float) -> dict:
        source = hit["_source"]
        return {
            "id": hit["_id"],
            "text": source["text"],
            "metadata": source.get("metadata", {}),
            "score": max(vector_score, keyword_score),
            "vector_score": vector_score,
            "keyword_score": keyword_score,
        }


def get_vector_backend() -> VectorBackend:
    if VECTOR_BACKEND == "elasticsearch":
        return ElasticsearchVectorBackend(ELASTICSEARCH_URL, ELASTICSEARCH_INDEX)
    if VECTOR_BACKEND == "memory":
        return MemoryVectorBackend()
    raise ValueError(f"不支持的向量后端: {VECTOR_BACKEND}")


def vector_search(query_vector: list[float], chunks: list[dict], top_k=3) -> list[dict]:
    vector_results = []
    for chunk in chunks:
        new_chunk = chunk.copy()
        new_chunk["score"] = cosine_similarity(query_vector, chunk["embedding"])
        vector_results.append(new_chunk)

    return sorted(vector_results, key=lambda x: x["score"], reverse=True)[:top_k]


def keyword_search(query: str, chunks: list[dict], top_k=3) -> list[dict]:
    if not query:
        return []

    results = []
    keywords = extract_keywords(query)
    for chunk in chunks:
        score = 0
        text: str = chunk["text"]
        if query in text:
            score += 3

        matched_keywords = []
        for kw in keywords:
            count = text.count(kw)
            if count > 0:
                matched_keywords.append(kw)
                score += 1
                score += min(count - 1, 2) * 0.25

        if score > 0:
            new_chunk = chunk.copy()
            new_chunk["score"] = min(score / 3.0, 1.0)
            new_chunk["matched_keywords"] = matched_keywords
            results.append(new_chunk)

    return sorted(
        results,
        key=lambda x: (x["score"] > 0, x["score"]),
        reverse=True,
    )[:top_k]


def merge_results(vector_results, keyword_results, top_k) -> list[dict]:
    final_results = {}
    for vr in vector_results:
        idx: str = vr["id"]
        final_results[idx] = {
            "id": idx,
            "text": vr["text"],
            "vector_score": vr.get("vector_score", vr["score"]),
            "keyword_score": 0,
            "score": 0,
            "metadata": vr["metadata"],
        }

    for kr in keyword_results:
        idx: str = kr["id"]
        if idx not in final_results:
            final_results[idx] = {
                "id": idx,
                "text": kr["text"],
                "vector_score": 0,
                "keyword_score": kr.get("keyword_score", kr["score"]),
                "score": 0,
                "metadata": kr["metadata"],
            }
        else:
            final_results[idx]["keyword_score"] = kr.get("keyword_score", kr["score"])

    results = []
    for item in final_results.values():
        item["score"] = item["vector_score"] * 0.6 + item["keyword_score"] * 0.4
        results.append(item)

    return sorted(
        results,
        key=lambda x: (x["keyword_score"] > 0, x["score"]),
        reverse=True,
    )[:top_k]


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot / (norm1 * norm2)


def extract_keywords(query: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z_/\-.0-9]+|[\u4e00-\u9fff]+", query)
    keywords = []

    for token in tokens:
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            if len(token) <= 2:
                keywords.append(token)
            else:
                keywords.extend(token[i:i + 2] for i in range(len(token) - 1))
        else:
            keywords.append(token)

    return list(dict.fromkeys(keywords))


backend = get_vector_backend()
