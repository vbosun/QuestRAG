from langchain.tools import tool
from langchain_core.documents import Document

from quest_rag.rag.embedding import vector_store

retriever = vector_store.as_retriever()
def search(query:str) -> list[Document]:
    '''向量相似度检索'''
    return retriever.invoke(query)






