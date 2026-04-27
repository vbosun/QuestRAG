from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

from quest_rag.config.config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_EMBEDDING_MODEL,
)

embeddings = OpenAIEmbeddings(
    base_url=OPENAI_BASE_URL,
    api_key=SecretStr(OPENAI_API_KEY),
    model=OPENAI_EMBEDDING_MODEL,
    check_embedding_ctx_length=False,
)

vector_store = InMemoryVectorStore(embeddings)

def add_documents(docs:list[Document]) -> list[str]:
    ''' 将文档存入向量库,返回文档ID列表 '''
    if not docs:
        return []
    return vector_store.add_documents(docs)
