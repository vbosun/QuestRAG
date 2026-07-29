import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from quest_rag.rag.document_embedding import add_documents, delete_documents
from quest_rag.rag.document_splitter import split_docs
from quest_rag.rag.loader import load_file


SUPPORTED_EXTENSIONS = {"txt", "pdf", "md"}


def ingest_file(path: Path) -> int:
    ext = path.suffix.lower().lstrip(".")
    if ext not in SUPPORTED_EXTENSIONS:
        print(f"skipped: {path.name}")
        return 0

    doc_id = f"kb::{path.name}"
    docs = load_file(str(path), ext)
    for doc in docs:
        doc.metadata = {
            **doc.metadata,
            "doc_id": doc_id,
            "filename": path.name,
            "source": str(path),
            "source_type": "knowledge_document",
            "ingested_at": datetime.now().isoformat(),
        }

    chunks = split_docs(docs)
    delete_documents(doc_id)
    ids = add_documents(chunks)
    print(f"ingested: {path.name} chunks={len(ids)}")
    return len(ids)


def main():
    documents_dir = ROOT_DIR / "documents"
    total = 0
    for path in sorted(documents_dir.iterdir()):
        if path.is_file():
            total += ingest_file(path)
    print(f"total_chunks: {total}")


if __name__ == "__main__":
    main()
