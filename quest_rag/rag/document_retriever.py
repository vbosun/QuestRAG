from langchain_core.documents import Document

from quest_rag.rag.document_embedding import get_embedding
from quest_rag.rag.vector_backend import (
    backend,
    cosine_similarity,
    extract_keywords,
    keyword_search,
    merge_results,
    vector_search,
)


def search(query: str, top_k=3) -> list[Document]:
    """向量相似度检索"""

    # 用户查询转为嵌入向量
    query_vector = get_embedding(query)

    return [
        Document(
            page_content=result["text"],
            metadata={
                **result["metadata"],
                "score": result["score"],
                "vector_score": result["vector_score"],
                "keyword_score": result["keyword_score"],
            },
        )
        for result in backend.search(query, query_vector, top_k)
    ]
