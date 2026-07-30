import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, UnstructuredMarkdownLoader
from langchain_core.documents import Document

MINERU_EXE = Path(r"D:\Software\Git\repository\zyzy\.venv-mineru-gpu\Scripts\mineru.exe")
MIN_TEXT_LENGTH = 30


def load_file(file_path:str, file_type: str = "auto") -> list[Document]:
    ''' 加载单个文件, 返回Document列表'''
    if file_type == "auto":
        file_type = file_path.rsplit(".", -1)[-1].lower()

    if file_type == "txt":
        return [_load_text_file(file_path)]
    elif file_type == "pdf":
        return load_pdf_with_mineru(file_path)
    elif file_type == "md":
        loader = UnstructuredMarkdownLoader(file_path)
    else:
        raise ValueError(f"不支持的文件类型: {file_type}")

    return loader.load()


def load_file_with_ocr_fallback(file_path: str, file_type: str = "auto") -> list[Document]:
    docs = load_file(file_path, file_type)
    resolved_type = file_type if file_type != "auto" else Path(file_path).suffix.lstrip(".").lower()
    if resolved_type != "pdf" or has_useful_text(docs):
        return docs
    return load_pdf_with_mineru(file_path)


def has_useful_text(docs: list[Document]) -> bool:
    text = "\n".join((doc.page_content or "").strip() for doc in docs)
    return len(text.strip()) >= MIN_TEXT_LENGTH


def load_pdf_with_mineru(file_path: str) -> list[Document]:
    if not MINERU_EXE.exists():
        return PyPDFLoader(file_path).load()

    output_dir = Path(tempfile.mkdtemp(prefix="questrag_mineru_"))
    try:
        env = os.environ.copy()
        env["NO_PROXY"] = "127.0.0.1,localhost"
        env["no_proxy"] = "127.0.0.1,localhost"
        subprocess.run(
            [
                str(MINERU_EXE),
                "-p",
                file_path,
                "-o",
                str(output_dir),
                "-b",
                "pipeline",
                "-m",
                "txt",
                "-l",
                "ch",
            ],
            check=True,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        markdown_files = sorted(output_dir.glob("*/txt/*.md"))
        if not markdown_files:
            return PyPDFLoader(file_path).load()
        text = markdown_files[0].read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            return PyPDFLoader(file_path).load()
        return [
            Document(
                page_content=text,
                metadata={"source": file_path, "loader": "mineru", "mineru_output": str(markdown_files[0])},
            )
        ]
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def _load_text_file(file_path: str) -> Document:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
        try:
            with open(file_path, encoding=encoding) as file:
                return Document(page_content=file.read(), metadata={"source": file_path})
        except UnicodeDecodeError:
            continue

    with open(file_path, encoding="utf-8", errors="replace") as file:
        return Document(page_content=file.read(), metadata={"source": file_path})




