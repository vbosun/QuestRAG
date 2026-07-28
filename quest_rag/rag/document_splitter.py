from langchain_core.documents import Document


def split_docs(docs: list[Document], chunk_size=50, chunk_overlap=20) -> list[Document]:
    ''' 分割加载的文档 '''
    if not docs or len(docs) == 0:
        return []

    all_splits = []

    # 拼接texts
    for doc in docs:
        text = doc.page_content
        metadata = doc.metadata

        chunks = _split_to_chunks(text, metadata, chunk_size, chunk_overlap)
        if len(chunks) > 0:
            all_splits.extend(chunks)

    return all_splits


def _split_to_chunks(text: str, metadata: dict, chunk_size=50, chunk_overlap=20) -> list[Document]:
    # 分块逻辑
    # 校验带分块文本是否为空
    if not text:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap 必须小于 chunk_size")
    # 定义分块结果数组
    chunks = []
    start = 0
    chunk_index = 0
    # 开始分块循环
    while start < len(text):
        # 分块结尾 = 分块起点+分块大小
        end = start + chunk_size
        chunk_text = text[start:end].strip()

        if chunk_text:
            chunk_metadata = metadata.copy()
            chunk_metadata["chunk_index"] = chunk_index
            chunk_metadata["start_index"] = start
            chunk_metadata["end_index"] = end
            chunks.append(Document(
                page_content=chunk_text,
                metadata=chunk_metadata,
            ))
        # 起点继续按分块重合大小滑动
        start = end - chunk_overlap

        if start < 0:
            start = 0
        chunk_index += 1

    return chunks
