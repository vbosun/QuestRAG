import asyncio
import sys
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

from quest_rag.rag import token_counter


def test_packaged_tokenizer_is_cached_and_counts_without_special_tokens(monkeypatch):
    loads = []
    encodes = []
    def encode(text, **kwargs):
        encodes.append((text, kwargs))
        return [1, 2, 3]
    tokenizer = SimpleNamespace(encode=encode)
    def load(path, **kwargs):
        loads.append((path, kwargs))
        return tokenizer
    monkeypatch.setattr(token_counter, "_tokenizer", None)
    monkeypatch.setenv("TOKENIZER_PATH", "/opt/questrag-tokenizer")
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(AutoTokenizer=SimpleNamespace(from_pretrained=load)))
    assert token_counter.count_tokens("") == 0
    assert loads == []
    assert token_counter.count_tokens("测试") == 3
    assert token_counter.count_tokens("again") == 3
    assert loads == [("/opt/questrag-tokenizer", {"trust_remote_code": False})]
    assert all(options == {"add_special_tokens": False} for _, options in encodes)


def test_tokenizer_failure_does_not_write_vectors(monkeypatch):
    from quest_rag.api import document
    from quest_rag.schemas.schemas import DocumentStageRequest
    upload = UploadFile(filename="token-check.md", file=BytesIO(b"# Token check\n\nTest content for ingestion."))
    stage = asyncio.run(document.stage_document(file=upload, current_user=object()))
    stage_id = stage.stage_id if hasattr(stage, "stage_id") else stage["stage_id"]
    written = []
    monkeypatch.setattr(document, "add_documents", lambda chunks: written.append(chunks))
    def fail(chunks):
        raise RuntimeError("tokenizer unavailable")
    monkeypatch.setattr(document, "_count_chunk_tokens", fail)
    try:
        req = DocumentStageRequest(stage_id=stage_id, metadata={"title": "Token check"}, clean_options={}, split_options={})
        with pytest.raises(HTTPException) as caught:
            document.commit_stage(req, SimpleNamespace(rag_scopes={"public_policy"}))
        assert caught.value.status_code == 500
        assert written == []
        assert stage_id in document._staged_documents
    finally:
        document._staged_documents.pop(stage_id, None)
