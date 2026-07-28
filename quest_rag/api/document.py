import os
import tempfile
import uuid
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, UploadFile
from logger import logger

from quest_rag.rag.document_embedding import add_documents
from quest_rag.rag.loader import load_file
from quest_rag.rag.document_splitter import split_docs
from quest_rag.rag.storage import (
    add_doc_metadata,
    delete_doc_metadata,
    get_all_docs,
    get_doc_by_id,
)
from quest_rag.schemas.schemas import (
    CommonResponse,
    DocInfo,
    DocMetadata,
    UploadResponse,
)

router = APIRouter(prefix="/documents", tags=["DOCUMENT"])

@router.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)):
    """上传文本文档"""
    filename = file.filename
    if not filename:
        return UploadResponse(
            success=False,
            doc_id="",
            chunk_count=0,
            message="文件名无效"
        )
    ext = filename.split('.')[-1].lower()
    if ext not in ["txt", "pdf", "md"]:
        raise HTTPException(status_code=400, detail="Unsupported file type. Only txt, pdf, md allowed.")

    content = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        docs = load_file(file_path=tmp_path, file_type=ext)
        doc_meta = docs[0].metadata
        doc_id = f"{uuid.uuid4().hex}_{file.filename}"
        doc_meta["doc_id"] = doc_id
        docs[0].metadata = doc_meta

        chunks = split_docs(docs=docs)
        ids = add_documents(chunks)
        print(f"ids: {ids}")

        doc = DocMetadata(
            doc_id=doc_id,
            filename=filename,
            chunk_count=len(ids),
            uploaded_at=datetime.now()
        )
        add_doc_metadata(doc)

        # 7. 返回结果
        return UploadResponse(
            success=True,
            doc_id=doc_id,
            chunk_count=len(ids),
            message="文档上传并且索引成功."
        )
    except Exception as e:
        logger.exception(str(e))

        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 清理临时文件
        os.unlink(tmp_path)


@router.post("/doclist", response_model=list[DocMetadata])
def doclist():
    """查看文档列表"""
    return get_all_docs()

@router.post("/deletedoc", response_model=CommonResponse)
def deletedoc(doc_info:DocInfo):
    """删除指定文档"""
    if not (doc_info and doc_info.id):
        raise HTTPException(status_code=500, detail="无效的文档ID")

    doc_meta = get_doc_by_id(doc_info.id)
    if doc_meta:
        delete_doc_metadata(doc_info.id)
    return CommonResponse(
        success=True,message=f"删除成功:{doc_info.id}"
    )


