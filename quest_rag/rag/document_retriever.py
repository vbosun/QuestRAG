from langchain_core.documents import Document

from quest_rag.core.config import get_retrieval_config
from quest_rag.rag.document_embedding import get_embedding
from quest_rag.rag.vector_backend import backend


def search(query: str, top_k: int | None = None) -> list[Document]:
    cfg = get_retrieval_config()
    if top_k is None:
        top_k = cfg["top_k"]

    query_vector = get_embedding(query)

    return [
        Document(
            page_content=result["text"],
            metadata={
                **result["metadata"],
                "score": result["score"],
                "vector_score": result.get("vector_score", 0),
                "keyword_score": result.get("keyword_score", 0),
            },
        )
        for result in backend.search_with_options(
            query,
            query_vector,
            top_k,
            mode=cfg["mode"],
            recall_k=cfg["recall_k"],
            rrf_k=cfg["rrf_k"],
        )
    ]
