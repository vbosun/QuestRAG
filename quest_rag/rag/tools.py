from langchain.tools import tool

from quest_rag.rag.retriever import search


@tool
def retrieve_context(query:str) -> str:
    """ 根据查询目标检索文档,返回查询结果 """
    docs = search(query)
    serialized = "\n\n".join(
        (f"来源: {doc.metadata["source"]}\n 内容: {doc.page_content}")
        for doc in docs
    )
    print(f"""
          query: {query}
          serialized: {serialized}

""")
    return serialized


# ── 工具列表 ──
tools = [retrieve_context]
