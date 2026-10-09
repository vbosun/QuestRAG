import asyncio
from io import BytesIO

import pytest
from fastapi import UploadFile

from quest_rag.rag.loader import load_file


@pytest.mark.parametrize("encoding", ["utf-8", "gb18030"])
def test_markdown_preserves_headings_tables_and_chinese(tmp_path, encoding):
    content = "# 上传验证\n\n## 办理材料\n\n| 材料 | 要求 |\n| --- | --- |\n| 测试文件 | 完整 |\n"
    path = tmp_path / "sample.md"
    path.write_bytes(content.encode(encoding))
    docs = load_file(str(path))
    assert len(docs) == 1
    assert docs[0].page_content == content
    assert docs[0].metadata["source"] == str(path)


def test_markdown_upload_generates_stage_without_indexing():
    from quest_rag.api.document import _staged_documents, stage_document

    content = "# 容器上传回归\n\n这是一份用于验证 Markdown 上传解析和分块预览的测试文档。\n"
    upload = UploadFile(filename="upload-check.md", file=BytesIO(content.encode("utf-8")))
    result = asyncio.run(stage_document(file=upload, current_user=object()))
    stage_id = result.stage_id if hasattr(result, "stage_id") else result["stage_id"]
    try:
        assert _staged_documents[stage_id]["docs"][0].page_content == content
        chunk_count = result.chunk_count if hasattr(result, "chunk_count") else result["chunk_count"]
        assert chunk_count > 0
    finally:
        _staged_documents.pop(stage_id, None)
