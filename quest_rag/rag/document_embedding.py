import httpx
from langchain_core.documents import Document
from openai import OpenAI

from quest_rag.core.config import (
    OPENAI_EMBEDDING_MODEL,
    EMBEDDING_BASE_URL
)
from quest_rag.rag.vector_backend import backend, vector_store

client = OpenAI(
    api_key="111",
    base_url=EMBEDDING_BASE_URL,
    # 绕过本地代理,避免访问本地服务失败(502)
    http_client=httpx.Client(trust_env=False),
)

embeddings = client.embeddings

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
    embeddings = [get_embedding(doc.page_content) for doc in docs]
    return backend.add_documents(docs, embeddings)


def delete_documents(doc_id: str):
    backend.delete_documents(doc_id)
