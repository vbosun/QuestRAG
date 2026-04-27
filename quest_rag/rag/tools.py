from langchain.tools import tool

from quest_rag.rag.retriever import search


@tool
def retrieve_context(query:str) -> str:
    """ 根据查询目标检索文档,返回查询结果 """
    docs = search(query)
    serialized = "\n\n".join(
        (f"Source: {doc.metadata}\nContent: {doc.page_content}")
        for doc in docs
    )
    return serialized


# ── 工具列表 ──
tools = [retrieve_context]
