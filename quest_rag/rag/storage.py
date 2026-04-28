
from quest_rag.schemas.schemas import DocMetadata

_doc_store: dict[str, DocMetadata] = {}


def add_doc_metadata(meta: DocMetadata):
    _doc_store[meta.doc_id] = meta

def get_all_docs() -> list[DocMetadata]:
    return list(_doc_store.values())

def get_doc_by_id(doc_id: str) -> DocMetadata | None:
    return _doc_store.get(doc_id)
def get_doc_by_name(doc_name: str) -> list[DocMetadata] | None:
    return [doc for doc in _doc_store.values()
            if doc_name in doc.filename.lower()]
def delete_doc_metadata(doc_id: str) -> bool:
    if doc_id in _doc_store:
        del _doc_store[doc_id]
        return True
    return False
