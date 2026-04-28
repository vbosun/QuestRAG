from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


def split_docs(docs:list[Document], chunk_size=50, chunk_overlap=20) -> list[Document]:
    ''' 分割加载的文档 '''
    if not docs or len(docs)==0:
        return []
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap, add_start_index=True
    )

    all_splits = text_splitter.split_documents(docs)
    return all_splits
