from uuid import uuid4

from langchain_core.documents import Document
from openai import OpenAI

from quest_rag.core.config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_EMBEDDING_MODEL,
    EMBEDDING_BASE_URL
)

client = OpenAI(
    api_key="111",
    base_url=EMBEDDING_BASE_URL,
    # 绕过本地代理,避免访问本地服务失败(502)
    # http_client=httpx.Client(trust_env=False),
)

embeddings = client.embeddings

vector_store: list[dict] = []


def get_embedding(text: str) -> list[float]:
    """ 调用embedding 模型, 把文本变成向量 """
    response = embeddings.create(
        model=OPENAI_EMBEDDING_MODEL,
        input=text,
    )

    return response.data[0].embedding


def add_documents(docs: list[Document]) -> list[str]:
    ''' 将文档存入向量库,返回文档ID列表 '''
    if not docs:
        return []
    ids = []
    for doc in docs:
        text = doc.page_content
        metadata = doc.metadata.copy()
        embedding = get_embedding(text)

        chunk_id = f"chunk_{uuid4().hex}"

        metadata["chunk_id"] = chunk_id

        vector_store.append({
            "id": chunk_id,
            "text": text,
            "embedding": embedding,
            "metadata": metadata
        })
        ids.append(chunk_id)

    return ids


def delete_documents(doc_id: str):
    ids_to_delete = [
        chunk["id"]
        for chunk in vector_store
        if chunk["metadata"]["doc_id"] == doc_id
    ]
    if not ids_to_delete:
        return

    # 切片赋值
    vector_store[:] = [
        chunk
        for chunk in vector_store
        if chunk["metadata"].get("doc_id") != doc_id
    ]
    return
