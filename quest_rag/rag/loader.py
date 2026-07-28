from langchain_community.document_loaders import PyPDFLoader, UnstructuredMarkdownLoader
from langchain_core.documents import Document


def load_file(file_path:str, file_type: str = "auto") -> list[Document]:
    ''' 加载单个文件, 返回Document列表'''
    if file_type == "auto":
        file_type = file_path.rsplit(".", -1)[-1].lower()

    if file_type == "txt":
        return [_load_text_file(file_path)]
    elif file_type == "pdf":
        loader = PyPDFLoader(file_path)
    elif file_type == "md":
        loader = UnstructuredMarkdownLoader(file_path)
    else:
        raise ValueError(f"不支持的文件类型: {file_type}")

    return loader.load()


def _load_text_file(file_path: str) -> Document:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
        try:
            with open(file_path, encoding=encoding) as file:
                return Document(page_content=file.read(), metadata={"source": file_path})
        except UnicodeDecodeError:
            continue

    with open(file_path, encoding="utf-8", errors="replace") as file:
        return Document(page_content=file.read(), metadata={"source": file_path})




