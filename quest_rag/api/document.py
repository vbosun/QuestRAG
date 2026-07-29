import os
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from langchain_core.documents import Document
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
from quest_rag.rag.vector_backend import backend
from quest_rag.schemas.schemas import (
    CommonResponse,
    CleanOptions,
    DocumentChunk,
    DocumentCommitResponse,
    DocumentMetadataInput,
    DocumentStageRequest,
    DocumentStageResponse,
    DocInfo,
    DocMetadata,
    SplitOptions,
    UploadResponse,
)

router = APIRouter(prefix="/documents", tags=["DOCUMENT"])
_staged_documents: dict[str, dict] = {}
SUPPORTED_TYPES = {"txt", "pdf", "md"}


@router.post("/stage", response_model=DocumentStageResponse)
async def stage_document(file: UploadFile = File(...)):
    """上传文档并生成入库预览，不立即写入知识库。"""
    filename = file.filename
    if not filename:
        raise HTTPException(status_code=400, detail="文件名无效")

    ext = filename.split(".")[-1].lower()
    if ext not in SUPPORTED_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type. Only txt, pdf, md allowed.")

    content = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        docs = load_file(file_path=tmp_path, file_type=ext)
    except Exception as e:
        logger.exception(str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        os.unlink(tmp_path)

    stage_id = uuid.uuid4().hex
    metadata = DocumentMetadataInput(title=Path(filename).stem)
    clean_options = CleanOptions()
    split_options = SplitOptions()
    _staged_documents[stage_id] = {
        "filename": filename,
        "file_type": ext,
        "file_size": len(content),
        "docs": docs,
    }
    return build_stage_response(stage_id, metadata, clean_options, split_options)


@router.post("/stage/preview", response_model=DocumentStageResponse)
def preview_stage(req: DocumentStageRequest):
    """根据当前元数据、清洗和分块参数重新生成预览。"""
    ensure_stage(req.stage_id)
    return build_stage_response(req.stage_id, req.metadata, req.clean_options, req.split_options)


@router.post("/stage/commit", response_model=DocumentCommitResponse)
def commit_stage(req: DocumentStageRequest):
    """确认入库：清洗、分块、向量化并写入知识库。"""
    stage = ensure_stage(req.stage_id)
    try:
        doc_id = build_doc_id(req.metadata.title or stage["filename"])
        if req.replace_doc_id and req.replace_doc_id == doc_id:
            doc_id = f"{doc_id}::{uuid.uuid4().hex[:8]}"

        docs = prepare_docs_for_ingest(req.stage_id, req.metadata, req.clean_options, doc_id)
        chunks = split_docs(
            docs=docs,
            chunk_size=req.split_options.chunk_size,
            chunk_overlap=req.split_options.chunk_overlap,
        )
        if req.split_options.attach_title:
            for chunk in chunks:
                chunk.page_content = f"{req.metadata.title}\n{chunk.page_content}"

        ids = add_documents(chunks)
        doc = DocMetadata(
            doc_id=doc_id,
            filename=req.metadata.title or stage["filename"],
            chunk_count=len(ids),
            uploaded_at=datetime.now(),
        )
        add_doc_metadata(doc)
        if req.replace_doc_id:
            delete_doc_metadata(req.replace_doc_id)
        _staged_documents.pop(req.stage_id, None)
        return DocumentCommitResponse(
            success=True,
            doc_id=doc_id,
            chunk_count=len(ids),
            message="文档已确认入库。",
        )
    except Exception as e:
        logger.exception(str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e

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
    if ext not in SUPPORTED_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type. Only txt, pdf, md allowed.")

    content = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        docs = load_file(file_path=tmp_path, file_type=ext)
        doc_id = f"{uuid.uuid4().hex}_{file.filename}"
        for doc_item in docs:
            doc_item.metadata = {
                **doc_item.metadata,
                "doc_id": doc_id,
                "filename": filename,
                "source_type": "knowledge_document",
            }

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


@router.post("/chunks", response_model=list[DocumentChunk])
def chunks(doc_info: DocInfo):
    """查看指定文档的分块列表。"""
    if not (doc_info and doc_info.id):
        raise HTTPException(status_code=400, detail="无效的文档ID")
    return backend.list_chunks(doc_info.id)

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


def ensure_stage(stage_id: str) -> dict:
    stage = _staged_documents.get(stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail="暂存文档不存在或已过期，请重新上传。")
    return stage


def build_stage_response(
    stage_id: str,
    metadata: DocumentMetadataInput,
    clean_options: CleanOptions,
    split_options: SplitOptions,
) -> DocumentStageResponse:
    stage = ensure_stage(stage_id)
    prepared_docs = prepare_docs_for_ingest(stage_id, metadata, clean_options)
    raw_text = "\n\n".join(doc.page_content for doc in stage["docs"])
    cleaned_text = "\n\n".join(doc.page_content for doc in prepared_docs)
    chunks = split_docs(
        docs=prepared_docs,
        chunk_size=split_options.chunk_size,
        chunk_overlap=split_options.chunk_overlap,
    )
    if split_options.attach_title:
        for chunk in chunks:
            chunk.page_content = f"{metadata.title}\n{chunk.page_content}"

    return DocumentStageResponse(
        stage_id=stage_id,
        filename=stage["filename"],
        file_type=stage["file_type"],
        file_size=stage["file_size"],
        page_count=len(stage["docs"]),
        metadata=metadata,
        clean_options=clean_options,
        split_options=split_options,
        raw_preview=raw_text[:1600],
        cleaned_preview=cleaned_text[:1600],
        chunk_count=len(chunks),
        chunk_preview=[
            {
                "index": index,
                "text": chunk.page_content[:500],
                "length": len(chunk.page_content),
                "page": chunk.metadata.get("page"),
                "chunk_index": chunk.metadata.get("chunk_index"),
            }
            for index, chunk in enumerate(chunks[:8], start=1)
        ],
    )


def prepare_docs_for_ingest(
    stage_id: str,
    metadata: DocumentMetadataInput,
    clean_options: CleanOptions,
    doc_id: str | None = None,
) -> list[Document]:
    stage = ensure_stage(stage_id)
    filename = stage["filename"]
    resolved_doc_id = doc_id or build_doc_id(metadata.title or Path(filename).stem)
    docs = []
    for doc in stage["docs"]:
        cleaned = clean_document_text(doc.page_content, clean_options)
        if not cleaned:
            continue
        docs.append(
            Document(
                page_content=cleaned,
                metadata={
                    **(doc.metadata or {}),
                    "doc_id": resolved_doc_id,
                    "filename": metadata.title or filename,
                    "original_filename": filename,
                    "source_type": "knowledge_document",
                    "document_category": metadata.category,
                    "organization": metadata.organization,
                    "publish_date": metadata.publish_date,
                    "region": metadata.region,
                    "keywords": metadata.keywords,
                    "notes": metadata.notes,
                },
            )
        )
    return docs


def build_doc_id(title: str) -> str:
    normalized = re.sub(r"\s+", " ", title).strip() or "未命名文档"
    return f"kb::{normalized}"


def clean_document_text(text: str, options: CleanOptions) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    lines = text.split("\n")
    if options.trim_lines:
        lines = [line.strip() for line in lines]
    if options.normalize_spaces:
        lines = [re.sub(r"[ \t]+", " ", line) for line in lines]
    text = "\n".join(lines)
    if options.merge_broken_lines:
        text = re.sub(r"(?<![。！？；：.!?;:])\n(?!\n)", "", text)
    if options.merge_blank_lines:
        text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


