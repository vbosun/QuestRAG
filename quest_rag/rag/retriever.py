from langchain.tools import tool
from langchain_core.documents import Document

from quest_rag.rag.embedding import vector_store


def search(query:str, k:int = 4) -> list[Document]:
    '''向量相似度检索'''
    return vector_store.similarity_search(query)

def search_with_score(query:str, k:int=4) -> list[tuple[Document, float]]:
    '''带分数的向量相似度检索'''    
    return vector_store.similarity_search_with_score(query) 



