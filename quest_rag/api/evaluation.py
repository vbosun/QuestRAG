import csv
import io
import re
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from langchain_core.documents import Document

from quest_rag.api.document import clean_document_text
from quest_rag.auth.dependencies import require_permission
from quest_rag.auth.schemas import CurrentUser
from quest_rag.core.config import MILVUS_HOST, MILVUS_PASSWORD, MILVUS_PORT, MILVUS_USER
from quest_rag.rag.document_embedding import get_embedding
from quest_rag.rag.document_splitter import split_docs
from quest_rag.rag.generator import generate_with_trace
from quest_rag.rag.job_retriever import search_jobs
from quest_rag.rag.loader import load_file_with_ocr_fallback
from quest_rag.rag.pg_store import (
    add_evaluation_items,
    create_evaluation_run,
    delete_evaluation_dataset,
    delete_evaluation_document,
    delete_evaluation_run,
    finish_evaluation_run,
    get_evaluation_dataset,
    get_evaluation_document,
    get_evaluation_run,
    init_db,
    list_evaluation_datasets,
    list_evaluation_documents,
    list_evaluation_runs,
    upsert_evaluation_dataset,
    upsert_evaluation_document,
)
from quest_rag.rag.vector_backend import MilvusVectorBackend
from quest_rag.evaluation_ragas import score_ragas_sample
from quest_rag.schemas.schemas import (
    CleanOptions,
    CommonResponse,
    EvaluationDatasetInput,
    EvaluationDocumentDetail,
    EvaluationDocumentSummary,
    EvaluationRunDetail,
    EvaluationRunRequest,
    EvaluationRunSummary,
)


router = APIRouter(prefix="/evaluations", tags=["EVALUATION"])
SUPPORTED_TYPES = {"txt", "pdf", "md"}
JOB_SOURCE_ID = "jobs::__pg_index__"
LEGACY_JOB_SOURCE_ID = "jobs::__es_index__"
BGE_M3_DIMS = 1024
DATASET_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "resources" / "templates" / "evaluation_dataset_template.csv"
DATASET_FIELDNAMES = [
    "ID",
    "用户问题",
    "期望答案要点",
    "必须覆盖要点",
    "禁止出现断言",
    "答案类型",
    "是否必须引用",
    "期望来源文档ID",
    "期望证据文本",
    "是否应拒答",
    "拒答原因",
    "评测重点",
    "备注",
]


def _eval_backend(collection_name: str) -> MilvusVectorBackend:
    return MilvusVectorBackend(MILVUS_HOST, MILVUS_PORT, collection_name, MILVUS_USER, MILVUS_PASSWORD)


@router.post("", response_model=list[EvaluationRunSummary])
def list_runs(current_user: CurrentUser = Depends(require_permission("evaluation.run.read"))):
    init_db()
    return list_evaluation_runs()


@router.post("/runs/get", response_model=EvaluationRunDetail)
def get_run(payload: dict, current_user: CurrentUser = Depends(require_permission("evaluation.run.read"))):
    init_db()
    run_id = payload["run_id"]
    run = get_evaluation_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="评测记录不存在")
    return run


@router.delete("/runs/delete", response_model=CommonResponse)
def delete_run(payload: dict, current_user: CurrentUser = Depends(require_permission("evaluation.run.delete"))):
    init_db()
    run_id = payload["run_id"]
    run = delete_evaluation_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="评测记录不存在")
    try:
        _eval_backend("").drop_collection(run["es_index_name"])
    except Exception:
        pass
    return CommonResponse(success=True, message="评测记录和临时集合已删除")


@router.post("/documents/list", response_model=list[EvaluationDocumentSummary])
def list_eval_documents(current_user: CurrentUser = Depends(require_permission("evaluation.run.read"))):
    init_db()
    runs = list_evaluation_runs()
    return [with_latest_eval_chunk_count(with_baseline_chunk_count(doc), runs) for doc in list_evaluation_documents()]


@router.post("/documents/upload", response_model=list[EvaluationDocumentSummary])
async def upload_eval_documents(files: list[UploadFile] = File(...), current_user: CurrentUser = Depends(require_permission("evaluation.document.manage"))):
    init_db()
    saved = []
    for file in files:
        saved.append(await save_eval_document(file))
    return [with_baseline_chunk_count(doc) for doc in saved]


@router.post("/documents/runs")
def list_eval_document_runs(payload: dict, current_user: CurrentUser = Depends(require_permission("evaluation.run.read"))):
    init_db()
    doc_id = payload["doc_id"]
    if not get_evaluation_document(doc_id):
        raise HTTPException(status_code=404, detail="评测文档不存在")
    runs = []
    for run in list_evaluation_runs():
        if not run_includes_doc(run, doc_id):
            continue
        runs.append(
            {
                "id": run["id"],
                "name": run["name"],
                "status": run["status"],
                "es_index_name": run["es_index_name"],
                "clean_options": run.get("clean_options", {}),
                "split_options": run.get("split_options", {}),
                "retrieval_options": run.get("retrieval_options", {}),
                "summary": run.get("summary", {}),
                "chunk_count": count_run_doc_chunks(run, doc_id),
                "created_at": run.get("created_at"),
                "completed_at": run.get("completed_at"),
            }
        )
    return runs


@router.post("/documents/runs/chunks")
def list_eval_document_run_chunks(payload: dict, current_user: CurrentUser = Depends(require_permission("evaluation.run.read"))):
    init_db()
    doc_id = payload["doc_id"]
    run_id = payload["run_id"]
    run = get_evaluation_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="评测记录不存在")
    if not run_includes_doc(run, doc_id):
        raise HTTPException(status_code=404, detail="该评测记录未使用此文档")
    backend = _eval_backend(run["es_index_name"])
    if not backend._mc.has_collection(run["es_index_name"]):
        return []
    return backend.list_chunks(doc_id)


@router.post("/documents/get", response_model=EvaluationDocumentDetail)
def get_eval_document(payload: dict, current_user: CurrentUser = Depends(require_permission("evaluation.run.read"))):
    init_db()
    doc_id = payload["doc_id"]
    doc = get_evaluation_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="评测文档不存在")
    chunks = build_baseline_chunks(doc)
    return {**with_baseline_chunk_count(doc), "chunks": chunks}


@router.delete("/documents/delete", response_model=CommonResponse)
def delete_eval_document(payload: dict, current_user: CurrentUser = Depends(require_permission("evaluation.document.manage"))):
    init_db()
    doc_id = payload["doc_id"]
    if not delete_evaluation_document(doc_id):
        raise HTTPException(status_code=404, detail="评测文档不存在")
    return CommonResponse(success=True, message="评测文档已删除")


@router.post("/datasets/list")
def list_datasets(current_user: CurrentUser = Depends(require_permission("evaluation.run.read"))):
    init_db()
    return list_evaluation_datasets()


@router.post("/datasets/import")
async def import_dataset(file: UploadFile = File(...), current_user: CurrentUser = Depends(require_permission("evaluation.dataset.manage"))):
    init_db()
    content = await file.read()
    text = content.decode("utf-8-sig")
    items = parse_dataset_csv(text, list_evaluation_documents())
    dataset_id = f"dataset_{uuid.uuid4().hex[:12]}"
    name = Path(file.filename or "评测集").stem
    record = {"id": dataset_id, "name": name, "items": items}
    upsert_evaluation_dataset(record)
    return get_evaluation_dataset(dataset_id)


@router.post("/datasets")
def create_dataset(req: EvaluationDatasetInput, current_user: CurrentUser = Depends(require_permission("evaluation.dataset.manage"))):
    init_db()
    dataset_id = f"dataset_{uuid.uuid4().hex[:12]}"
    upsert_evaluation_dataset({"id": dataset_id, "name": req.name, "items": [item.model_dump() for item in req.items]})
    return get_evaluation_dataset(dataset_id)


@router.post("/datasets/get")
def get_dataset(payload: dict, current_user: CurrentUser = Depends(require_permission("evaluation.run.read"))):
    init_db()
    dataset_id = payload["dataset_id"]
    dataset = get_evaluation_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="评测集不存在")
    return dataset


@router.put("/datasets/update")
def update_dataset(payload: dict, current_user: CurrentUser = Depends(require_permission("evaluation.dataset.manage"))):
    init_db()
    dataset_id = payload["dataset_id"]
    name = payload["name"]
    items = payload.get("items", [])
    if not get_evaluation_dataset(dataset_id):
        raise HTTPException(status_code=404, detail="评测集不存在")
    upsert_evaluation_dataset({"id": dataset_id, "name": name, "items": items})
    return get_evaluation_dataset(dataset_id)


@router.delete("/datasets/delete", response_model=CommonResponse)
def delete_dataset(payload: dict, current_user: CurrentUser = Depends(require_permission("evaluation.dataset.manage"))):
    init_db()
    dataset_id = payload["dataset_id"]
    if not delete_evaluation_dataset(dataset_id):
        raise HTTPException(status_code=404, detail="评测集不存在")
    return CommonResponse(success=True, message="评测集已删除")


@router.post("/datasets/export")
def export_dataset(payload: dict, current_user: CurrentUser = Depends(require_permission("evaluation.run.read"))):
    init_db()
    dataset_id = payload["dataset_id"]
    dataset = get_evaluation_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="评测集不存在")
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=DATASET_FIELDNAMES,
    )
    writer.writeheader()
    for item in dataset.get("items", []):
        writer.writerow(
            {
                "ID": item.get("id", ""),
                "用户问题": item.get("question", ""),
                "期望答案要点": item.get("expected_answer", ""),
                "必须覆盖要点": ";".join(item.get("required_points", [])),
                "禁止出现断言": ";".join(item.get("forbidden_claims", [])),
                "答案类型": item.get("answer_type", ""),
                "是否必须引用": "是" if item.get("expected_citation_required") else "否",
                "期望来源文档ID": ";".join(item.get("expected_source_ids", [])),
                "期望证据文本": item.get("expected_evidence", ""),
                "是否应拒答": "是" if item.get("should_refuse") else "否",
                "拒答原因": item.get("refusal_reason", ""),
                "评测重点": item.get("focus", ""),
                "备注": item.get("note", ""),
            }
        )
    return Response(
        content="﻿" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f"attachment; filename=dataset.csv; "
                f"filename*=UTF-8''{quote(str(dataset['name']))}.csv"
            )
        },
    )


@router.post("/datasets/template")
def download_dataset_template(current_user: CurrentUser = Depends(require_permission("evaluation.run.read"))):
    if not DATASET_TEMPLATE_PATH.exists():
        raise HTTPException(status_code=404, detail="评测集模板不存在")
    return Response(
        content="﻿" + DATASET_TEMPLATE_PATH.read_text(encoding="utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                "attachment; filename=evaluation_dataset_template.csv; "
                "filename*=UTF-8''QuestRAG-%E8%AF%84%E6%B5%8B%E9%9B%86%E6%A8%A1%E6%9D%BF.csv"
            )
        },
    )


@router.post("/run", response_model=EvaluationRunDetail)
def run_evaluation(req: EvaluationRunRequest, current_user: CurrentUser = Depends(require_permission("evaluation.run.create"))):
    init_db()
    dataset = get_evaluation_dataset(req.dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="请选择有效评测集")

    eval_id = f"eval_{uuid.uuid4().hex[:12]}"
    index_name = f"questrag_{eval_id}"
    scope_doc_ids = req.document_ids or [doc["id"] for doc in list_evaluation_documents()]
    record = {
        "id": eval_id,
        "name": req.name,
        "status": "running",
        "dataset_path": dataset["name"],
        "es_index_name": index_name,
        "retrieval_index_name": index_name,
        "evaluation_mode": req.evaluation_mode,
        "document_scope": {"mode": "selected" if req.document_ids else "all", "doc_ids": scope_doc_ids},
        "clean_options": req.clean_options.model_dump(),
        "split_options": req.split_options.model_dump(),
        "retrieval_options": req.retrieval_options.model_dump(),
        "generation_options": req.generation_options.model_dump(),
        "ragas_options": req.ragas_options.model_dump(),
        "summary": {},
    }
    create_evaluation_run(record)

    eval_backend = _eval_backend(index_name)
    eval_backend.create_eval_collection(index_name, dims=BGE_M3_DIMS)
    try:
        indexed_chunks = index_eval_documents(eval_backend, scope_doc_ids, req.clean_options, req.split_options)
        items = evaluate_items(
            eval_id,
            eval_backend,
            dataset.get("items", []),
            req.retrieval_options,
            evaluation_mode=req.evaluation_mode,
            generation_options=req.generation_options.model_dump(),
            ragas_options=req.ragas_options.model_dump(),
            current_user=current_user,
        )
        add_evaluation_items(items)
        summary = build_summary(items, len(indexed_chunks), len(scope_doc_ids))
        finish_evaluation_run(eval_id, status="completed", summary=summary)
    except Exception as exc:
        finish_evaluation_run(eval_id, status="failed", summary={}, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    run = get_evaluation_run(eval_id)
    if not run:
        raise HTTPException(status_code=500, detail="评测记录保存失败")
    return run


async def save_eval_document(file: UploadFile) -> dict:
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
        docs = load_file_with_ocr_fallback(tmp_path, ext)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    doc_id = f"evaldoc::{uuid.uuid4().hex[:12]}::{Path(filename).stem}"
    raw_pages = [{"text": doc.page_content, "metadata": doc.metadata or {}} for doc in docs]
    raw_text = "\n\n".join(page["text"] for page in raw_pages)
    record = {
        "id": doc_id,
        "filename": filename,
        "title": Path(filename).stem,
        "file_type": ext,
        "file_size": len(content),
        "raw_text": raw_text,
        "raw_pages": raw_pages,
        "metadata": {},
    }
    upsert_evaluation_document(record)
    return record


def with_baseline_chunk_count(doc: dict) -> dict:
    if "raw_pages" in doc:
        chunk_count = len(build_baseline_chunks(doc))
    else:
        chunk_count = int((doc.get("metadata") or {}).get("baseline_chunk_count") or 0)
    return {**doc, "chunk_count": chunk_count}


def with_latest_eval_chunk_count(doc: dict, runs: list[dict]) -> dict:
    for run in runs:
        if not run_includes_doc(run, doc["id"]):
            continue
        return {
            **doc,
            "latest_eval_run_id": run["id"],
            "latest_eval_run_name": run["name"],
            "latest_eval_chunk_count": count_run_doc_chunks(run, doc["id"]),
        }
    return doc


def run_includes_doc(run: dict, doc_id: str) -> bool:
    scope = run.get("document_scope") or {}
    return doc_id in (scope.get("doc_ids") or [])


def count_run_doc_chunks(run: dict, doc_id: str) -> int:
    try:
        backend = _eval_backend(run["es_index_name"])
        if not backend._mc.has_collection(run["es_index_name"]):
            return 0
        return backend.count_chunks_by_doc(run["es_index_name"], doc_id)
    except Exception:
        return 0


def build_baseline_chunks(doc: dict) -> list[dict]:
    source_docs = doc_to_documents(doc, CleanOptions())
    chunks = split_docs(source_docs, chunk_size=500, chunk_overlap=100, strategy="fixed")
    return [
        {
            "chunk_id": f"{doc['id']}::baseline::{index}",
            "text": chunk.page_content,
            "metadata": {**chunk.metadata, "chunk_index": index},
            "length": len(chunk.page_content),
        }
        for index, chunk in enumerate(chunks)
    ]


def index_eval_documents(eval_backend: MilvusVectorBackend, doc_ids: list[str], clean_options, split_options) -> list[str]:
    all_chunks: list[Document] = []
    for doc_id in doc_ids:
        doc = get_evaluation_document(doc_id)
        if not doc:
            continue
        source_docs = doc_to_documents(doc, clean_options)
        chunks = split_docs(source_docs, chunk_size=split_options.chunk_size, chunk_overlap=split_options.chunk_overlap, strategy=split_options.strategy, separator_preset=split_options.separator_preset)
        if split_options.attach_title:
            for chunk in chunks:
                chunk.page_content = f"{doc['title']}\n{chunk.page_content}"
        all_chunks.extend(chunks)
    embeddings = [get_embedding(chunk.page_content) for chunk in all_chunks]
    return eval_backend.add_documents(all_chunks, embeddings)


def doc_to_documents(doc: dict, clean_options: CleanOptions) -> list[Document]:
    return [
        Document(
            page_content=clean_document_text(page.get("text", ""), clean_options),
            metadata={
                **(page.get("metadata") or {}),
                "doc_id": doc["id"],
                "filename": doc["title"],
                "source_type": "evaluation_document",
            },
        )
        for page in doc.get("raw_pages", [])
        if clean_document_text(page.get("text", ""), clean_options)
    ]


def parse_dataset_csv(text: str, documents: list[dict] | None = None) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(text)))
    resolver = build_source_resolver(documents or [])
    items = []
    for index, row in enumerate(rows, start=1):
        question = get_first(row, ["用户问题", "question", "问题"]) or ""
        row_id = get_first(row, ["ID", "id"]) or f"Q{index:04d}"
        if row_id == "ID" and question in {"用户问题", "question", "问题"}:
            continue
        if not question:
            continue
        items.append(
            {
                "id": row_id,
                "question": question,
                "expected_answer": get_first(row, ["期望答案要点", "expected_answer", "answer"]) or "",
                "required_points": parse_refs(get_first(row, ["必须覆盖要点", "required_points", "required_points_cn"]) or ""),
                "forbidden_claims": parse_refs(get_first(row, ["禁止出现断言", "forbidden_claims", "forbidden_claims_cn"]) or ""),
                "answer_type": get_first(row, ["答案类型", "answer_type", "type"]) or "",
                "expected_citation_required": parse_bool(get_first(row, ["是否必须引用", "expected_citation_required", "citation_required"]) or ""),
                "expected_source_ids": resolve_source_ids(
                    parse_refs(get_first(row, ["期望来源文档ID", "期望来源/文档", "source_id", "sourceid"]) or ""),
                    resolver,
                ),
                "expected_evidence": get_first(row, ["期望证据文本", "expected_evidence", "evidence"]) or "",
                "should_refuse": parse_bool(get_first(row, ["是否应拒答", "should_refuse"]) or ""),
                "refusal_reason": get_first(row, ["拒答原因", "refusal_reason"]) or "",
                "focus": get_first(row, ["评测重点", "focus"]) or "",
                "note": get_first(row, ["备注", "note"]) or "",
            }
        )
    return items


def evaluate_items(
    eval_id: str,
    eval_backend: MilvusVectorBackend,
    rows: list[dict],
    options,
    *,
    evaluation_mode: str = "retrieval",
    generation_options: dict | None = None,
    ragas_options: dict | None = None,
    current_user: CurrentUser | None = None,
) -> list[dict]:
    items = []
    run_retrieval = evaluation_mode in {"retrieval", "both"}
    run_generation = evaluation_mode in {"generation", "both"}
    retrieval_options = options.model_dump() if hasattr(options, "model_dump") else dict(options)
    for index, row in enumerate(rows, start=1):
        if not (row.get("question") or "").strip():
            continue
        expected_source_ids = normalize_source_ids(row.get("expected_source_ids", []))
        query_text = row["question"]
        retrieval_queries: list[dict] = []
        retrieved: list[dict] = []
        metrics: dict = {}
        if run_retrieval:
            retrieval_queries, retrieved, metrics = run_retrieval_eval(query_text, expected_source_ids, row, options, eval_backend)

        generated_answer = None
        answer_citations: list[dict] = []
        tool_calls: list[dict] = []
        generation_metrics: dict = {}
        ragas_metrics: dict = {}
        generation_error = None
        latency_ms = None
        if run_generation:
            started = time.perf_counter()
            try:
                generation = generate_with_trace(
                    query_text,
                    thread_id=f"{eval_id}:{row.get('id') or index}",
                    current_user=current_user,
                    generation_options=generation_options,
                    eval_backend=eval_backend,
                    retrieval_options=retrieval_options,
                )
                generated_answer = generation.get("answer") or ""
                answer_citations = generation.get("citations") or []
                tool_calls = generation.get("tool_calls") or []
                retrieval_queries.extend(build_tool_query_snapshots(tool_calls, options))
                contexts = contexts_from_tool_calls(tool_calls)
                ragas_metrics = score_ragas_sample(
                    question=query_text,
                    answer=generated_answer,
                    contexts=contexts,
                    reference=row.get("expected_answer"),
                    options=ragas_options or {},
                    generation_options=generation_options or {},
                )
                generation_metrics = calculate_generation_metrics(
                    generated_answer,
                    answer_citations,
                    row,
                    ragas_metrics,
                )
            except Exception as exc:
                generation_error = str(exc)
                generation_metrics = {"passed": False, "error": generation_error}
            finally:
                latency_ms = int((time.perf_counter() - started) * 1000)

        items.append(
            {
                "id": f"{eval_id}_item_{index:04d}",
                "run_id": eval_id,
                "question_id": row.get("id") or f"Q{index:04d}",
                "question": row["question"],
                "expected_answer": row.get("expected_answer"),
                "required_points": row.get("required_points", []),
                "forbidden_claims": row.get("forbidden_claims", []),
                "answer_type": row.get("answer_type"),
                "expected_citation_required": bool(row.get("expected_citation_required")),
                "expected_source_ids": expected_source_ids,
                "expected_chunk_ids": [],
                "expected_chunk_text": row.get("expected_evidence", ""),
                "should_refuse": bool(row.get("should_refuse")),
                "refusal_reason": row.get("refusal_reason"),
                "retrieval_queries": retrieval_queries,
                "retrieved": retrieved,
                "metrics": metrics,
                "generated_answer": generated_answer,
                "answer_citations": answer_citations,
                "tool_calls": tool_calls,
                "generation_metrics": generation_metrics,
                "ragas_metrics": ragas_metrics,
                "generation_error": generation_error,
                "latency_ms": latency_ms,
            }
        )
    return items


def run_retrieval_eval(query_text: str, expected_source_ids: list[str], row: dict, options, eval_backend: MilvusVectorBackend) -> tuple[list[dict], list[dict], dict]:
    if JOB_SOURCE_ID in expected_source_ids:
        retrieval_queries = [
            build_retrieval_query_snapshot(
                query=query_text,
                target="jobs",
                options=options,
            )
        ]
        results = search_jobs(query_text, options.top_k)
        retrieved = [serialize_job_result(result, rank) for rank, result in enumerate(results, start=1)]
    else:
        retrieval_queries = [
            build_retrieval_query_snapshot(
                query=query_text,
                target="evaluation_documents",
                options=options,
            )
        ]
        query_vector = get_embedding(query_text)
        results = eval_backend.search_with_options(
            query_text,
            query_vector,
            options.top_k,
            mode=options.mode,
            recall_k=options.recall_k,
            rrf_k=options.rrf_k,
        )
        retrieved = [serialize_result(result, rank) for rank, result in enumerate(results, start=1)]
    metrics = calculate_metrics(
        retrieved,
        expected_source_ids,
        row.get("expected_evidence", ""),
        options.top_k,
        should_refuse=bool(row.get("should_refuse")),
    )
    return retrieval_queries, retrieved, metrics


def build_retrieval_query_snapshot(query: str, target: str, options) -> dict:
    return {
        "type": "original",
        "query": query,
        "target": target,
        "top_k": options.top_k,
        "recall_k": getattr(options, "recall_k", None) or options.top_k,
        "mode": options.mode,
        "rrf_k": getattr(options, "rrf_k", None) or 60,
    }


def build_tool_query_snapshots(tool_calls: list[dict], options) -> list[dict]:
    snapshots = []
    for call in tool_calls:
        query = call.get("query")
        if not query:
            continue
        snapshots.append(
            {
                "type": "agent_tool",
                "tool_name": call.get("tool_name"),
                "query": query,
                "target": call.get("target"),
                "top_k": call.get("top_k") or getattr(options, "top_k", None),
                "recall_k": getattr(options, "recall_k", None) or getattr(options, "top_k", None),
                "mode": getattr(options, "mode", None),
                "rrf_k": getattr(options, "rrf_k", None) or 60,
            }
        )
    return snapshots


def contexts_from_tool_calls(tool_calls: list[dict]) -> list[str]:
    contexts = []
    for call in tool_calls:
        for context in call.get("contexts", []) or []:
            text = context.get("text") if isinstance(context, dict) else None
            if isinstance(text, str) and text.strip():
                contexts.append(text)
    return contexts


def calculate_generation_metrics(answer: str, citations: list[dict], row: dict, ragas_metrics: dict) -> dict:
    should_refuse = bool(row.get("should_refuse"))
    refused = looks_like_refusal(answer)
    labels = {str(citation.get("label")) for citation in citations if citation.get("label")}
    used_labels = set(re.findall(r"【([^】]+)】", answer or ""))
    citation_valid = not used_labels or used_labels.issubset(labels)
    citation_required = bool(row.get("expected_citation_required"))
    citation_required_hit = bool(used_labels) if citation_required else None
    expected_answer = row.get("expected_answer") or ""
    expected_score = text_overlap(expected_answer, answer) if expected_answer else None
    required_points = row.get("required_points") or []
    required_point_scores = [
        {"point": point, "covered": text_overlap(point, answer) >= 0.5}
        for point in required_points
        if point
    ]
    forbidden_claims = row.get("forbidden_claims") or []
    forbidden_hits = [
        claim
        for claim in forbidden_claims
        if claim and text_overlap(claim, answer) >= 0.65
    ]
    numeric_ragas = [float(value) for value in ragas_metrics.values() if isinstance(value, (int, float))]
    ragas_average = round(sum(numeric_ragas) / len(numeric_ragas), 4) if numeric_ragas else None
    if should_refuse:
        passed = refused
    else:
        required_points_hit = all(item["covered"] for item in required_point_scores)
        passed = bool(answer.strip()) and citation_valid and (citation_required_hit is not False) and required_points_hit and not forbidden_hits and not refused
    return {
        "should_refuse": should_refuse,
        "refusal_reason": row.get("refusal_reason") or None,
        "refusal_hit": refused if should_refuse else None,
        "has_answer": bool(answer.strip()),
        "citation_valid": citation_valid,
        "citation_required": citation_required,
        "citation_required_hit": citation_required_hit,
        "used_citation_labels": sorted(used_labels),
        "available_citation_labels": sorted(labels),
        "expected_answer_overlap": round(expected_score, 4) if expected_score is not None else None,
        "required_points_total": len(required_point_scores),
        "required_points_hit": sum(1 for item in required_point_scores if item["covered"]),
        "required_points_detail": required_point_scores,
        "forbidden_claims_hit": forbidden_hits,
        "answer_type": row.get("answer_type") or None,
        "ragas_average": ragas_average,
        "passed": passed,
    }


def looks_like_refusal(answer: str) -> bool:
    compact = re.sub(r"\s+", "", answer or "")
    refusal_terms = [
        "无法回答",
        "不能回答",
        "没有符合条件的资料",
        "未检索到",
        "资料不足",
        "无法确认",
        "不能编造",
    ]
    return any(term in compact for term in refusal_terms)


def calculate_metrics(
    retrieved: list[dict],
    expected_source_ids: list[str],
    expected_evidence: str,
    top_k: int,
    should_refuse: bool = False,
) -> dict:
    if should_refuse:
        refusal_hit = len(retrieved) == 0
        return {
            "should_refuse": True,
            "refusal_hit": refusal_hit,
            "source_hit": None,
            "evidence_hit": None,
            "source_rank": None,
            "evidence_rank": None,
            "evidence_score": 0,
            "mrr": 1 if refusal_hit else 0,
            "top_k": top_k,
        }

    source_ids = set(expected_source_ids)
    source_rank = next((item["rank"] for item in retrieved if item.get("doc_id") in source_ids), None)
    evidence_rank = None
    evidence_score = 0
    if expected_evidence:
        scored = [(item["rank"], text_overlap(expected_evidence, item.get("text", ""))) for item in retrieved]
        evidence_rank, evidence_score = next(((rank, score) for rank, score in scored if score >= 0.35), (None, max([score for _, score in scored], default=0)))
    best_rank = evidence_rank or source_rank
    return {
        "source_hit": source_rank is not None,
        "evidence_hit": evidence_rank is not None,
        "source_rank": source_rank,
        "evidence_rank": evidence_rank,
        "evidence_score": round(evidence_score, 4),
        "mrr": round(1 / best_rank, 6) if best_rank else 0,
        "top_k": top_k,
    }


def serialize_result(result: dict, rank: int) -> dict:
    metadata = result.get("metadata", {})
    return {
        "rank": rank,
        "chunk_id": result.get("id") or metadata.get("chunk_id"),
        "doc_id": metadata.get("doc_id"),
        "filename": metadata.get("filename") or metadata.get("source"),
        "text": result.get("text", ""),
        "score": round(float(result.get("score", 0)), 6),
        "vector_score": round(float(result.get("vector_score", 0)), 6),
        "keyword_score": round(float(result.get("keyword_score", 0)), 6),
        "metadata": metadata,
    }


def serialize_job_result(job: dict, rank: int) -> dict:
    text = "\n".join(
        [
            f"岗位: {job.get('title') or ''}",
            f"单位: {job.get('company') or ''}",
            f"地点: {job.get('address') or ''}",
            f"薪资: {job.get('salary') or ''}",
            f"学历: {job.get('education') or ''}",
            f"经验: {job.get('experience') or ''}",
            f"行业: {job.get('industry') or ''}",
            f"类别: {job.get('category') or ''}",
            f"招聘人数: {job.get('headcount') or ''}",
            f"来源: {job.get('source') or ''}",
        ]
    )
    return {
        "rank": rank,
        "chunk_id": job.get("id"),
        "doc_id": JOB_SOURCE_ID,
        "filename": "岗位库（PG）",
        "text": text,
        "score": round(float(job.get("score", 0)), 6),
        "vector_score": round(float(job.get("vector_score", 0)), 6),
        "keyword_score": round(float(job.get("keyword_score", 0)), 6),
        "metadata": {
            "source_type": "job",
            "job_id": job.get("id"),
            "title": job.get("title"),
            "company": job.get("company"),
            "address": job.get("address"),
            "salary": job.get("salary"),
            "education": job.get("education"),
            "experience": job.get("experience"),
            "industry": job.get("industry"),
            "category": job.get("category"),
            "headcount": job.get("headcount"),
            "updated": job.get("updated"),
            "source": job.get("source"),
            "url": job.get("url"),
        },
    }


def build_summary(items: list[dict], chunk_count: int, document_count: int) -> dict:
    total = len(items)
    if not total:
        return {"question_count": 0, "document_count": document_count, "chunk_count": chunk_count}
    retrieval_scored_items = [item for item in items if item.get("metrics")]
    refusal_items = [item for item in retrieval_scored_items if item["metrics"].get("should_refuse")]
    retrieval_items = [item for item in retrieval_scored_items if not item["metrics"].get("should_refuse")]
    retrieval_total = len(retrieval_items)
    refusal_total = len(refusal_items)
    source_hits = sum(1 for item in retrieval_items if item["metrics"].get("source_hit"))
    evidence_hits = sum(1 for item in retrieval_items if item["metrics"].get("evidence_hit"))
    refusal_hits = sum(1 for item in refusal_items if item["metrics"].get("refusal_hit"))
    avg_mrr = sum(float(item["metrics"].get("mrr", 0)) for item in retrieval_items) / retrieval_total if retrieval_total else 0
    pass_count = evidence_hits + refusal_hits
    generation_items = [item for item in items if item.get("generation_metrics")]
    generation_total = len(generation_items)
    generation_pass = sum(1 for item in generation_items if item["generation_metrics"].get("passed"))
    generation_errors = sum(1 for item in generation_items if item.get("generation_error"))
    ragas_scores = [
        float(item["generation_metrics"]["ragas_average"])
        for item in generation_items
        if isinstance(item.get("generation_metrics", {}).get("ragas_average"), (int, float))
    ]
    return {
        "question_count": total,
        "retrieval_question_count": retrieval_total,
        "refusal_question_count": refusal_total,
        "document_count": document_count,
        "chunk_count": chunk_count,
        "source_hit_rate": round(source_hits / retrieval_total, 4) if retrieval_total else None,
        "evidence_hit_rate": round(evidence_hits / retrieval_total, 4) if retrieval_total else None,
        "refusal_hit_rate": round(refusal_hits / refusal_total, 4) if refusal_total else None,
        "retrieval_pass_rate": round(pass_count / len(retrieval_scored_items), 4) if retrieval_scored_items else None,
        "generation_question_count": generation_total,
        "generation_pass_rate": round(generation_pass / generation_total, 4) if generation_total else None,
        "generation_error_count": generation_errors,
        "ragas_average": round(sum(ragas_scores) / len(ragas_scores), 4) if ragas_scores else None,
        "pass_rate": round(pass_count / len(retrieval_scored_items), 4) if retrieval_scored_items else None,
        "mrr": round(avg_mrr, 4),
        "miss_count": len(retrieval_scored_items) - pass_count if retrieval_scored_items else None,
    }


def get_first(row: dict, keys: list[str]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value:
            return value
    return None


def parse_refs(value: str) -> list[str]:
    return [token.strip() for token in re.split(r"[;；,\n]", value) if token.strip()]


def build_source_resolver(documents: list[dict]) -> dict[str, str]:
    resolver = {
        JOB_SOURCE_ID: JOB_SOURCE_ID,
        LEGACY_JOB_SOURCE_ID: JOB_SOURCE_ID,
        "岗位库": JOB_SOURCE_ID,
        "岗位库（PG）": JOB_SOURCE_ID,
        "岗位库(PG)": JOB_SOURCE_ID,
        "gansu_jobs_raw.json": JOB_SOURCE_ID,
        "gansu_jobs_raw": JOB_SOURCE_ID,
    }
    for doc in documents:
        doc_id = doc.get("id")
        if not doc_id:
            continue
        candidates = {
            str(doc_id),
            str(doc.get("title") or ""),
            str(doc.get("filename") or ""),
            Path(str(doc.get("filename") or "")).stem,
        }
        for candidate in candidates:
            if candidate:
                resolver[candidate] = str(doc_id)
    return resolver


def resolve_source_ids(values: list[str], resolver: dict[str, str]) -> list[str]:
    resolved = []
    for value in normalize_source_ids(values):
        resolved.append(resolver.get(value, value))
    return resolved


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"是", "true", "1", "yes", "y"}


def normalize_source_ids(values: list[str]) -> list[str]:
    return [JOB_SOURCE_ID if value == LEGACY_JOB_SOURCE_ID else value for value in values]


def text_overlap(expected: str, actual: str) -> float:
    expected_terms = set(make_bigrams(expected))
    actual_terms = set(make_bigrams(actual))
    if not expected_terms or not actual_terms:
        return 0
    return len(expected_terms & actual_terms) / len(expected_terms)


def make_bigrams(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", text)
    if len(compact) <= 2:
        return [compact] if compact else []
    return [compact[index : index + 2] for index in range(len(compact) - 1)]
