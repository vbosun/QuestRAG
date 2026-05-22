from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    UnstructuredMarkdownLoader,
)
from langchain_core.documents import Document


def load_file(file_path:str, file_type: str = "auto") -> list[Document]:
    ''' 加载单个文件, 返回Document列表'''
    loaders = {
        "txt": TextLoader,
        "pdf": PyPDFLoader,
        "md": UnstructuredMarkdownLoader,
    }

    if file_type == "auto":
        file_type = file_path.rsplit(".", -1)[-1].lower()
    loader_cls = loaders.get(file_type)
    if not loader_cls:
        raise ValueError(f"不支持的文件类型: {file_type}")
    loader = loader_cls(file_path,"UTF-8")
    return loader.load()




