import math
import re
from abc import ABC, abstractmethod
from datetime import datetime
from uuid import uuid4

from langchain_core.documents import Document

from quest_rag.core.config import (
    ELASTICSEARCH_INDEX,
    ELASTICSEARCH_URL,
    MILVUS_COLLECTION_NAME,
    MILVUS_HOST,
    MILVUS_PASSWORD,
    MILVUS_PORT,
    MILVUS_USER,
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
    def search_with_options(
        self,
        query: str,
        query_vector: list[float],
        top_k: int,
        mode: str = "hybrid",
        recall_k: int | None = None,
        rrf_k: int = 60,
    ) -> list[dict]:
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

    def search_with_options(
        self,
        query: str,
        query_vector: list[float],
        top_k: int,
        mode: str = "hybrid",
        recall_k: int | None = None,
        rrf_k: int = 60,
    ) -> list[dict]:
        mode = mode if mode in {"hybrid", "vector", "keyword"} else "hybrid"
        recall = recall_k or top_k
        vector_results = [] if mode == "keyword" else vector_search(query_vector, vector_store, recall)
        keyword_results = [] if mode == "vector" else keyword_search(query, vector_store, recall)
        return merge_results(vector_results, keyword_results, top_k, rrf_k=rrf_k)

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
                    "strategy": metadata.get("strategy") or "fixed",
                    "separator_preset": metadata.get("separator_preset") or "general",
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

    def search_with_options(
        self,
        query: str,
        query_vector: list[float],
        top_k: int,
        mode: str = "hybrid",
        recall_k: int | None = None,
        rrf_k: int = 60,
    ) -> list[dict]:
        mode = mode if mode in {"hybrid", "vector", "keyword"} else "hybrid"
        recall = recall_k or top_k
        vector_results = [] if mode == "keyword" else self._vector_search(query_vector, recall)
        keyword_results = [] if mode == "vector" else self._keyword_search(query, recall)
        return merge_results(
            vector_results,
            keyword_results,
            top_k,
            rrf_k=rrf_k,
        )

    def delete_index(self):
        self.client.indices.delete(index=self.index_name, ignore_unavailable=True)

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
                                        "metadata.strategy",
                                        "metadata.separator_preset",
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
                    "strategy": metadata.get("strategy") or "fixed",
                    "separator_preset": metadata.get("separator_preset") or "general",
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
            self._hit_to_chunk(hit, vector_score=hit["_score"] - 1.0)
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
        return [
            self._hit_to_chunk(hit, keyword_score=hit["_score"])
            for hit in response["hits"]["hits"]
        ]

    def _hit_to_chunk(self, hit: dict, vector_score: float = 0, keyword_score: float = 0) -> dict:
        source = hit["_source"]
        return {
            "id": hit["_id"],
            "text": source["text"],
            "metadata": source.get("metadata", {}),
            "vector_score": vector_score,
            "keyword_score": keyword_score,
        }


class MilvusVectorBackend(VectorBackend):
    def __init__(self, host: str, port: str, collection_name: str, user: str = "", password: str = ""):
        self._host = host
        self._port = port
        self._collection_name = collection_name
        self._user = user
        self._password = password
        self._client = None

    @property
    def _mc(self):
        if self._client is None:
            from pymilvus import MilvusClient

            uri = f"http://{self._host}:{self._port}"
            client_kwargs = {"uri": uri}
            if self._user and self._password:
                client_kwargs["user"] = self._user
                client_kwargs["password"] = self._password
            self._client = MilvusClient(**client_kwargs)
        return self._client

    def add_documents(self, docs: list[Document], embeddings: list[list[float]]) -> list[str]:
        if not docs:
            return []
        ids = []
        rows = []
        for doc, embedding in zip(docs, embeddings, strict=True):
            chunk_id = f"chunk_{uuid4().hex}"
            metadata = doc.metadata.copy()
            metadata["chunk_id"] = chunk_id
            rows.append({
                "id": chunk_id,
                "text": doc.page_content,
                "embedding": embedding,
                "doc_id": metadata.get("doc_id", ""),
                "filename": metadata.get("filename", ""),
                "chunk_index": metadata.get("chunk_index", 0),
                "metadata": metadata,
            })
            ids.append(chunk_id)
        self._mc.insert(collection_name=self._collection_name, data=rows)
        return ids

    def delete_documents(self, doc_id: str):
        self._mc.delete(
            collection_name=self._collection_name,
            filter=f'doc_id == "{doc_id}"',
        )

    def search(self, query: str, query_vector: list[float], top_k: int) -> list[dict]:
        return self.search_with_options(query, query_vector, top_k)

    def search_with_options(
        self,
        query: str,
        query_vector: list[float],
        top_k: int,
        mode: str = "hybrid",
        recall_k: int | None = None,
        rrf_k: int = 60,
    ) -> list[dict]:
        mode = mode if mode in {"hybrid", "vector", "keyword"} else "hybrid"
        recall = recall_k or top_k
        vector_results = [] if mode == "keyword" else self._vector_search(query_vector, recall)
        keyword_results = [] if mode == "vector" else self._keyword_search(query, recall)
        return merge_results(vector_results, keyword_results, top_k, rrf_k=rrf_k)

    def _vector_search(self, query_vector: list[float], top_k: int) -> list[dict]:
        results = self._mc.search(
            collection_name=self._collection_name,
            data=[query_vector],
            anns_field="embedding",
            search_params={"metric_type": "COSINE"},
            limit=top_k,
            output_fields=["id", "text", "doc_id", "filename", "chunk_index", "metadata"],
        )
        return [
            {
                "id": hit["id"],
                "text": hit["entity"].get("text", ""),
                "metadata": hit["entity"].get("metadata", {}),
                "vector_score": hit["distance"],
                "keyword_score": 0,
            }
            for hit in results[0]
        ]

    def _keyword_search(self, query: str, top_k: int) -> list[dict]:
        if not query:
            return []
        escaped = query.replace('"', '\\"')
        results = self._mc.query(
            collection_name=self._collection_name,
            filter=f'text like "%{escaped}%"',
            output_fields=["id", "text", "doc_id", "filename", "chunk_index", "metadata"],
            limit=top_k,
        )
        return [
            {
                "id": r["id"],
                "text": r.get("text", ""),
                "metadata": r.get("metadata", {}),
                "vector_score": 0,
                "keyword_score": 1.0,
            }
            for r in results
        ]

    def list_documents(self) -> list[dict]:
        results = self._mc.query(
            collection_name=self._collection_name,
            filter="id != ''",
            output_fields=["doc_id", "filename", "metadata"],
            limit=10000,
        )
        docs_map: dict[str, dict] = {}
        for r in results:
            doc_id = r.get("doc_id", "")
            if not doc_id:
                continue
            if doc_id not in docs_map:
                meta = r.get("metadata", {})
                docs_map[doc_id] = {
                    "doc_id": doc_id,
                    "filename": meta.get("filename") or r.get("filename") or doc_id,
                    "chunk_count": 0,
                    "uploaded_at": meta.get("ingested_at") or datetime.now().isoformat(),
                    "strategy": meta.get("strategy") or "fixed",
                    "separator_preset": meta.get("separator_preset") or "general",
                }
            docs_map[doc_id]["chunk_count"] += 1
        return list(docs_map.values())

    def list_chunks(self, doc_id: str) -> list[dict]:
        results = self._mc.query(
            collection_name=self._collection_name,
            filter=f'doc_id == "{doc_id}"',
            output_fields=["id", "text", "metadata", "chunk_index"],
            limit=10000,
        )
        chunks = [
            {
                "chunk_id": r["id"],
                "text": r.get("text", ""),
                "metadata": r.get("metadata", {}),
                "length": len(r.get("text", "")),
            }
            for r in results
        ]
        return sorted(chunks, key=lambda c: c["metadata"].get("chunk_index", 0))

    def create_eval_collection(self, name: str, dims: int):
        """为评测创建临时集合。"""
        from pymilvus import DataType, FieldSchema

        if self._mc.has_collection(name):
            self._mc.drop_collection(name)

        schema = self._mc.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=256))
        schema.add_field(FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535))
        schema.add_field(FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dims))
        schema.add_field(FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=256))
        schema.add_field(FieldSchema(name="filename", dtype=DataType.VARCHAR, max_length=512))
        schema.add_field(FieldSchema(name="chunk_index", dtype=DataType.INT64))
        schema.add_field(FieldSchema(name="metadata", dtype=DataType.JSON))

        index_params = self._mc.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="IVF_FLAT",
            metric_type="COSINE",
            params={"nlist": 128},
        )

        self._mc.create_collection(
            collection_name=name, schema=schema, index_params=index_params
        )

    def drop_collection(self, name: str):
        self._mc.drop_collection(name)

    def count_chunks_by_doc(self, collection_name: str, doc_id: str) -> int:
        results = self._mc.query(
            collection_name=collection_name,
            filter=f'doc_id == "{doc_id}"',
            output_fields=["id"],
        )
        return len(results)


def get_vector_backend() -> VectorBackend:
    if VECTOR_BACKEND == "elasticsearch":
        return ElasticsearchVectorBackend(ELASTICSEARCH_URL, ELASTICSEARCH_INDEX)
    if VECTOR_BACKEND == "milvus":
        return MilvusVectorBackend(
            host=MILVUS_HOST,
            port=MILVUS_PORT,
            collection_name=MILVUS_COLLECTION_NAME,
            user=MILVUS_USER,
            password=MILVUS_PASSWORD,
        )
    if VECTOR_BACKEND == "memory":
        return MemoryVectorBackend()
    raise ValueError(f"不支持的向量后端: {VECTOR_BACKEND}")


def vector_search(query_vector: list[float], chunks: list[dict], top_k=3) -> list[dict]:
    scored = [(cosine_similarity(query_vector, c["embedding"]), c) for c in chunks]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{**c, "vector_score": s, "keyword_score": 0} for s, c in scored[:top_k]]


def keyword_search(query: str, chunks: list[dict], top_k=3) -> list[dict]:
    if not query:
        return []

    keywords = extract_keywords(query)
    scored = []
    for chunk in chunks:
        text: str = chunk["text"]
        if query in text:
            scored.append((3, {**chunk, "keyword_score": 3, "vector_score": 0}))
            continue

        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            scored.append((hits, {**chunk, "keyword_score": hits, "vector_score": 0}))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def merge_results(
    vector_results,
    keyword_results,
    top_k,
    rrf_k: int = 60,
) -> list[dict]:
    """RRF（倒数排名融合）——只看排名不看分数，绕开分数量纲不可比问题。"""
    rrf_scores: dict[str, float] = {}
    doc_map: dict[str, dict] = {}

    for rank, vr in enumerate(vector_results, start=1):
        idx: str = vr["id"]
        rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (rrf_k + rank)
        if idx not in doc_map:
            doc_map[idx] = {
                "id": idx,
                "text": vr["text"],
                "metadata": vr["metadata"],
                "vector_score": vr.get("vector_score", 0),
                "keyword_score": vr.get("keyword_score", 0),
            }
        else:
            doc_map[idx]["vector_score"] = vr.get("vector_score", 0)

    for rank, kr in enumerate(keyword_results, start=1):
        idx: str = kr["id"]
        rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (rrf_k + rank)
        if idx not in doc_map:
            doc_map[idx] = {
                "id": idx,
                "text": kr["text"],
                "metadata": kr["metadata"],
                "vector_score": kr.get("vector_score", 0),
                "keyword_score": kr.get("keyword_score", 0),
            }
        else:
            doc_map[idx]["keyword_score"] = kr.get("keyword_score", 0)

    sorted_ids = sorted(rrf_scores, key=lambda i: rrf_scores[i], reverse=True)

    results = []
    for idx in sorted_ids[:top_k]:
        doc = doc_map[idx]
        doc["score"] = round(rrf_scores[idx], 6)
        results.append(doc)

    return results


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot / (norm1 * norm2)


def extract_keywords(query: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z_/\-.0-9]+|[一-鿿]+", query)
    keywords = []

    for token in tokens:
        if re.fullmatch(r"[一-鿿]+", token):
            if len(token) <= 2:
                keywords.append(token)
            else:
                keywords.extend(token[i:i + 2] for i in range(len(token) - 1))
        else:
            keywords.append(token)

    return list(dict.fromkeys(keywords))


backend = get_vector_backend()
