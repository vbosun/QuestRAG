
from quest_rag.rag.document_embedding import delete_documents
from quest_rag.rag.vector_backend import backend
from quest_rag.schemas.schemas import DocMetadata

_doc_store: dict[str, DocMetadata] = {}
_doc_store_loaded = False


def _load_doc_store_once():
    global _doc_store_loaded
    if _doc_store_loaded:
        return
    for item in backend.list_documents():
        meta = DocMetadata(**item)
        _doc_store[meta.doc_id] = meta
    _doc_store_loaded = True


def add_doc_metadata(meta: DocMetadata):
    _doc_store[meta.doc_id] = meta

def get_all_docs() -> list[DocMetadata]:
    _load_doc_store_once()
    return list(_doc_store.values())

def get_doc_by_id(doc_id: str) -> DocMetadata | None:
    _load_doc_store_once()
    return _doc_store.get(doc_id)
def get_doc_by_name(doc_name: str) -> list[DocMetadata]:
    _load_doc_store_once()
    normalized_name = doc_name.lower()
    return [doc for doc in _doc_store.values()
            if normalized_name in doc.filename.lower()]
def delete_doc_metadata(doc_id: str) -> bool:
    _load_doc_store_once()
    if doc_id not in _doc_store:
        return False
    del _doc_store[doc_id]
    delete_documents(doc_id)
    return True
