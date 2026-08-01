import json
import math
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING
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

if TYPE_CHECKING:
    from quest_rag.rag.retrieval_permissions import RetrievalPermissionFilter


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
        permission_filter: "RetrievalPermissionFilter | None" = None,
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
        permission_filter: "RetrievalPermissionFilter | None" = None,
    ) -> list[dict]:
        mode = mode if mode in {"hybrid", "vector", "keyword"} else "hybrid"
        recall = recall_k or top_k

        store = vector_store
        if permission_filter and permission_filter.is_empty:
            return []
        if permission_filter and permission_filter.scope_codes:
            store = [
                c for c in vector_store
                if c.get("metadata", {}).get("scope_code") in permission_filter.scope_codes
            ]

        vector_results = [] if mode == "keyword" else vector_search(query_vector, store, recall)
        keyword_results = [] if mode == "vector" else keyword_search(query, store, recall)
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
                    "scope_code": metadata.get("scope_code") or "public_policy",
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
        permission_filter: "RetrievalPermissionFilter | None" = None,
    ) -> list[dict]:
        mode = mode if mode in {"hybrid", "vector", "keyword"} else "hybrid"
        recall = recall_k or top_k
        if permission_filter and permission_filter.is_empty:
            return []
        es_filter = _build_es_filter(permission_filter)
        vector_results = [] if mode == "keyword" else self._vector_search(query_vector, recall, es_filter)
        keyword_results = [] if mode == "vector" else self._keyword_search(query, recall, es_filter)
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
                                        "metadata.scope_code",
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
                    "scope_code": metadata.get("scope_code") or "public_policy",
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
                            "scope_code": {"type": "keyword"},
                            "visibility": {"type": "keyword"},
                            "security_level": {"type": "keyword"},
                            "owner_user_id": {"type": "keyword"},
                            "department_id": {"type": "keyword"},
                            "chunk_index": {"type": "integer"},
                            "start_index": {"type": "integer"},
                            "end_index": {"type": "integer"},
                        }
                    },
                }
            },
        )

    def _vector_search(self, query_vector: list[float], top_k: int, es_filter: list[dict] | None = None) -> list[dict]:
        filter_clause = es_filter if es_filter else [{"match_all": {}}]
        response = self.client.search(
            index=self.index_name,
            size=top_k,
            query={
                "script_score": {
                    "query": {"bool": {"filter": filter_clause}},
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

    def _keyword_search(self, query: str, top_k: int, es_filter: list[dict] | None = None) -> list[dict]:
        if not query:
            return []
        query_body: dict = {"match": {"text": query}}
        if es_filter:
            query_body = {"bool": {"must": query_body, "filter": es_filter}}
        response = self.client.search(
            index=self.index_name,
            size=top_k,
            query=query_body,
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
    # 适配实际 Milvus collection schema（metadata_json 为 JSON 字符串，非 JSON 类型字段）
    _QUERY_CORE = ["id", "text", "metadata_json"]
    _QUERY_DOCS = ["id", "doc_id", "filename", "metadata_json"]
    _QUERY_CHUNKS = ["id", "text", "metadata_json", "chunk_index"]

    def __init__(self, host: str, port: str, collection_name: str, user: str = "", password: str = ""):
        self._host = host
        self._port = port
        self._collection_name = collection_name
        self._user = user
        self._password = password
        self._client = None
        self._text_index_ensured = False
        self._analyzer_enabled = False

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

    # ── metadata_json 转换 ──────────────────────────────────────

    @staticmethod
    def _parse_metadata(row: dict) -> dict:
        val = row.get("metadata_json", "{}")
        if isinstance(val, dict):
            return val
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    # ── VectorBackend 接口 ──────────────────────────────────────

    def add_documents(self, docs: list[Document], embeddings: list[list[float]]) -> list[str]:
        if not docs:
            return []
        ids = []
        rows = []
        insert_fields = self._field_names()
        for doc, embedding in zip(docs, embeddings, strict=True):
            chunk_id = f"chunk_{uuid4().hex}"
            metadata = doc.metadata.copy()
            metadata["chunk_id"] = chunk_id
            row = _doc_to_milvus_row(chunk_id, doc.page_content, embedding, metadata)
            rows.append({k: v for k, v in row.items() if k in insert_fields})
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
        permission_filter: "RetrievalPermissionFilter | None" = None,
    ) -> list[dict]:
        mode = mode if mode in {"hybrid", "vector", "keyword"} else "hybrid"
        recall = recall_k or top_k
        if permission_filter and permission_filter.is_empty:
            return []
        milvus_filter = _build_milvus_filter_expr(permission_filter, self._field_names())
        vector_results = [] if mode == "keyword" else self._vector_search(query_vector, recall, milvus_filter)
        keyword_results = [] if mode == "vector" else self._keyword_search(query, recall, milvus_filter)
        results = merge_results(vector_results, keyword_results, top_k, rrf_k=rrf_k)
        return _apply_permission_filter(results, permission_filter)

    def _field_names(self) -> set[str]:
        try:
            desc = self._mc.describe_collection(self._collection_name)
            return {field["name"] for field in desc.get("fields", [])}
        except Exception:
            return {
                "id", "text", "embedding", "chunk_id", "doc_id", "chunk_index",
                "filename", "source_type", "metadata_json",
            }

    def _vector_search(self, query_vector: list[float], top_k: int, milvus_filter: str | None = None) -> list[dict]:
        kwargs = {}
        if milvus_filter:
            kwargs["filter"] = milvus_filter
        results = self._mc.search(
            collection_name=self._collection_name,
            data=[query_vector],
            anns_field="embedding",
            search_params={"metric_type": "COSINE"},
            limit=top_k,
            output_fields=self._QUERY_CORE,
            **kwargs,
        )
        return [
            {
                "id": hit["id"],
                "text": hit["entity"].get("text", ""),
                "metadata": self._parse_metadata(hit["entity"]),
                "vector_score": hit["distance"],
                "keyword_score": 0,
            }
            for hit in results[0]
        ]

    def _ensure_text_index(self) -> bool:
        """确保 text 字段启用 analyzer + enable_match + INVERTED 索引。

        现有 collection 如果 text 字段创建时未设 enable_match=True
        则无法使用 text_match，此方法返回 False，调用方应降级到 LIKE。
        """
        if self._text_index_ensured:
            return self._analyzer_enabled
        try:
            desc = self._mc.describe_collection(self._collection_name)
            text_field = next((f for f in desc["fields"] if f["name"] == "text"), None)
            if text_field is None:
                self._analyzer_enabled = False
                return False
            # text_match 需要 enable_match（以及 enable_analyzer）
            params = text_field.get("params", {})
            self._analyzer_enabled = params.get("enable_match") in (True, "true")

            if self._analyzer_enabled:
                indexes = self._mc.list_indexes(self._collection_name)
                if not any(
                    idx.get("field_name") == "text" and idx.get("index_type") == "INVERTED"
                    for idx in indexes
                ):
                    idx_params = self._mc.prepare_index_params()
                    idx_params.add_index(field_name="text", index_type="INVERTED")
                    self._mc.create_index(self._collection_name, idx_params)
        except Exception:
            self._analyzer_enabled = False
        finally:
            self._text_index_ensured = True
        return self._analyzer_enabled

    def _keyword_search(self, query: str, top_k: int, milvus_filter: str | None = None) -> list[dict]:
        if not query:
            return []
        escaped = query.replace('"', '\\"')

        if self._ensure_text_index():
            filter_expr = f'text_match(text, "{escaped}")'
            if milvus_filter:
                filter_expr = f"({milvus_filter}) and {filter_expr}"
            results = self._mc.query(
                collection_name=self._collection_name,
                filter=filter_expr,
                output_fields=self._QUERY_CORE,
                limit=top_k,
            )
            return [
                {
                    "id": r["id"],
                    "text": r.get("text", ""),
                    "metadata": self._parse_metadata(r),
                    "vector_score": 0,
                    "keyword_score": 1.0,
                }
                for r in results
            ]

        # 降级路径：LIKE 子串匹配（旧 collection 未启用 text_match）
        like_expr = f'text like "%{escaped}%"'
        if milvus_filter:
            like_expr = f"({milvus_filter}) and {like_expr}"
        results = self._mc.query(
            collection_name=self._collection_name,
            filter=like_expr,
            output_fields=self._QUERY_CORE,
            limit=top_k,
        )
        return [
            {
                "id": r["id"],
                "text": r.get("text", ""),
                "metadata": self._parse_metadata(r),
                "vector_score": 0,
                "keyword_score": 1.0,
            }
            for r in results
        ]

    def list_documents(self) -> list[dict]:
        results = self._mc.query(
            collection_name=self._collection_name,
            filter="id != ''",
            output_fields=self._QUERY_DOCS,
            limit=10000,
        )
        docs_map: dict[str, dict] = {}
        for r in results:
            doc_id = r.get("doc_id", "")
            if not doc_id:
                continue
            if doc_id not in docs_map:
                meta = self._parse_metadata(r)
                docs_map[doc_id] = {
                    "doc_id": doc_id,
                    "filename": meta.get("filename") or r.get("filename") or doc_id,
                    "chunk_count": 0,
                    "uploaded_at": meta.get("ingested_at") or datetime.now().isoformat(),
                    "scope_code": meta.get("scope_code") or "public_policy",
                    "strategy": meta.get("strategy") or "fixed",
                    "separator_preset": meta.get("separator_preset") or "general",
                }
            docs_map[doc_id]["chunk_count"] += 1
        return list(docs_map.values())

    def list_chunks(self, doc_id: str) -> list[dict]:
        results = self._mc.query(
            collection_name=self._collection_name,
            filter=f'doc_id == "{doc_id}"',
            output_fields=self._QUERY_CHUNKS,
            limit=10000,
        )
        chunks = [
            {
                "chunk_id": r["id"],
                "text": r.get("text", ""),
                "metadata": self._parse_metadata(r),
                "length": len(r.get("text", "")),
            }
            for r in results
        ]
        return sorted(chunks, key=lambda c: c["metadata"].get("chunk_index", 0))

    # ── 评测临时集合 ────────────────────────────────────────────

    def create_eval_collection(self, name: str, dims: int):
        from pymilvus import DataType

        if self._mc.has_collection(name):
            self._mc.drop_collection(name)

        schema = self._mc.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=128)
        schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=65535, enable_analyzer=True, enable_match=True, analyzer_params={"tokenizer": "jieba"})
        schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=dims)
        schema.add_field(field_name="chunk_id", datatype=DataType.VARCHAR, max_length=256)
        schema.add_field(field_name="doc_id", datatype=DataType.VARCHAR, max_length=256)
        schema.add_field(field_name="chunk_index", datatype=DataType.INT64)
        schema.add_field(field_name="filename", datatype=DataType.VARCHAR, max_length=512)
        schema.add_field(field_name="source_type", datatype=DataType.VARCHAR, max_length=128)
        schema.add_field(field_name="metadata_json", datatype=DataType.VARCHAR, max_length=65535)

        index_params = self._mc.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="IVF_FLAT",
            metric_type="COSINE",
            params={"nlist": 128},
        )
        index_params.add_index(field_name="text", index_type="INVERTED")

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

    def migrate_to_fulltext(self, target_name: str | None = None, batch_size: int = 500) -> dict:
        """将当前 collection 迁移到启用全文检索的新 collection。

        新 collection 的 text 字段带 enable_analyzer + enable_match + jieba 分词器，
        迁移完成后需手动切换到新 collection。
        """
        from pymilvus import DataType

        source = self._collection_name
        target = target_name or f"{source}_v2"

        if not self._mc.has_collection(source):
            raise RuntimeError(f"源 collection '{source}' 不存在")
        if self._mc.has_collection(target):
            raise RuntimeError(f"目标 collection '{target}' 已存在，请先删除")

        # 1. 读取旧 schema
        desc = self._mc.describe_collection(source)
        old_fields = desc["fields"]
        auto_id = desc.get("auto_id", False)
        emb_dim = 1024
        for f in old_fields:
            if f["name"] == "embedding":
                emb_dim = f.get("params", {}).get("dim", 1024)
                break

        # 2. 构建新 schema（text 字段启用 analyzer）
        schema = self._mc.create_schema(auto_id=auto_id, enable_dynamic_field=False)
        for f in old_fields:
            kwargs: dict = {}
            params = f.get("params", {})
            if f["type"] == DataType.VARCHAR:
                kwargs["max_length"] = params.get("max_length", 65535)
                if f["name"] == "text":
                    kwargs["enable_analyzer"] = True
                    kwargs["enable_match"] = True
                    kwargs["analyzer_params"] = {"tokenizer": "jieba"}
            elif f["type"] == DataType.FLOAT_VECTOR:
                kwargs["dim"] = emb_dim
            schema.add_field(
                field_name=f["name"],
                datatype=f["type"],
                is_primary=f.get("is_primary", False),
                auto_id=f.get("auto_id", False),
                **kwargs,
            )

        # 3. 建索引
        idx_params = self._mc.prepare_index_params()
        idx_params.add_index(
            field_name="embedding",
            index_type="IVF_FLAT",
            metric_type="COSINE",
            params={"nlist": 128},
        )
        idx_params.add_index(field_name="text", index_type="INVERTED")

        # 4. 创建新 collection
        self._mc.create_collection(collection_name=target, schema=schema, index_params=idx_params)

        # 5. 获取字段名列表，分批迁移数据
        field_names = [f["name"] for f in old_fields]

        offset = 0
        migrated = 0
        while True:
            batch = self._mc.query(
                collection_name=source,
                filter="id != ''",
                output_fields=field_names,
                limit=batch_size,
                offset=offset,
            )
            if not batch:
                break
            self._mc.insert(collection_name=target, data=batch)
            migrated += len(batch)
            offset += len(batch)
            print(f"  migrated {migrated} chunks...")

        self._mc.flush(target)

        # 6. 验证
        src_count = self._mc.get_collection_stats(source)["row_count"]
        tgt_count = self._mc.get_collection_stats(target)["row_count"]

        return {
            "source": source,
            "source_rows": src_count,
            "target": target,
            "target_rows": tgt_count,
            "migrated": migrated,
        }


def _build_es_filter(permission_filter: "RetrievalPermissionFilter | None") -> list[dict] | None:
    if permission_filter is None:
        return None
    filters = []
    if permission_filter.scope_codes:
        filters.append({"terms": {"metadata.scope_code": permission_filter.scope_codes}})
    if permission_filter.doc_ids:
        filters.append({"terms": {"metadata.doc_id": permission_filter.doc_ids}})
    return filters or None


def _build_milvus_filter_expr(
    permission_filter: "RetrievalPermissionFilter | None",
    available_fields: set[str] | None = None,
) -> str | None:
    if permission_filter is None:
        return None
    parts = []
    if permission_filter.scope_codes and (available_fields is None or "scope_code" in available_fields):
        quoted = ", ".join(f'"{s}"' for s in permission_filter.scope_codes)
        parts.append(f"scope_code in [{quoted}]")
    if permission_filter.doc_ids and (available_fields is None or "doc_id" in available_fields):
        quoted = ", ".join(f'"{d}"' for d in permission_filter.doc_ids)
        parts.append(f"doc_id in [{quoted}]")
    if not parts:
        return None
    return " and ".join(f"({p})" for p in parts)


def _apply_permission_filter(
    results: list[dict],
    permission_filter: "RetrievalPermissionFilter | None",
) -> list[dict]:
    if permission_filter is None:
        return results
    allowed_scopes = set(permission_filter.scope_codes)
    allowed_doc_ids = set(permission_filter.doc_ids or [])
    filtered = []
    for result in results:
        metadata = result.get("metadata") or {}
        if allowed_scopes and metadata.get("scope_code", "public_policy") not in allowed_scopes:
            continue
        if allowed_doc_ids and metadata.get("doc_id") not in allowed_doc_ids:
            continue
        filtered.append(result)
    return filtered


def _doc_to_milvus_row(chunk_id: str, text: str, embedding: list[float], metadata: dict) -> dict:
    """将 Document + embedding 映射为 Milvus collection 的实际字段。"""
    return {
        "id": chunk_id,
        "text": text,
        "embedding": embedding,
        "chunk_id": chunk_id,
        "doc_id": metadata.get("doc_id", ""),
        "chunk_index": metadata.get("chunk_index", 0),
        "filename": metadata.get("filename", ""),
        "title": str(metadata.get("title", "")),
        "source": str(metadata.get("source", "")),
        "source_type": str(metadata.get("source_type", "")),
        "start_index": int(metadata.get("start_index", 0)),
        "end_index": int(metadata.get("end_index", 0)),
        "page": int(metadata.get("page", 0)),
        "total_pages": int(metadata.get("total_pages", 0)),
        "creationdate": str(metadata.get("creationdate", "")),
        "creator": str(metadata.get("creator", "")),
        "organization": str(metadata.get("organization", "")),
        "region": str(metadata.get("region", "")),
        "heading_path": json.dumps(metadata.get("heading_path", []), ensure_ascii=False),
        "ingested_at": str(metadata.get("ingested_at", "")),
        "loader": str(metadata.get("loader", "")),
        "moddate": str(metadata.get("moddate", "")),
        "original_filename": str(metadata.get("original_filename", "")),
        "producer": str(metadata.get("producer", "")),
        "document_category": str(metadata.get("document_category", "")),
        "mineru_output": str(metadata.get("mineru_output", "")),
        "page_label": str(metadata.get("page_label", "")),
        "scope_code": str(metadata.get("scope_code", "public_policy")),
        "visibility": str(metadata.get("visibility", "PUBLIC")),
        "security_level": str(metadata.get("security_level", "PUBLIC")),
        "owner_user_id": str(metadata.get("owner_user_id", "")),
        "department_id": str(metadata.get("department_id", "")),
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
    }


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
