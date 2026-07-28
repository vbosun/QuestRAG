from langchain.tools import tool

from quest_rag.rag.document_retriever import search
from quest_rag.rag.result_validator import validate_search_result
from quest_rag.rag.storage import get_all_docs, get_doc_by_name
from quest_rag.schemas.schemas import DocMetadata


@tool
def retrieve_context(query:str) -> str:
    """ 根据查询目标检索文档,返回查询结果 """
    docs = search(query)

    # 对检索结果进行校验
    results = validate_search_result(docs,0.75)

    serialized = "\n\n".join(
        (f"来源: {doc["metadata"]["source"]}\n 内容: {doc["text"]}")
        for doc in results
    )
    print(f"""
          query: {query}
          serialized: {serialized}

""")
    return serialized


@tool
def get_document_list(name:str|None) -> list[DocMetadata]|None:
    """
    获取文档信息列表。

    如果不提供名称，则返回所有文档的元数据列表；
    如果提供名称，则返回文档名称中包含该字符串的文档信息（模糊匹配）。
    """
    if not name:
        return get_all_docs()
    else:
        return get_doc_by_name(name)

# ── 工具列表 ──
tools = [retrieve_context, get_document_list]
