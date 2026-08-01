import csv
import io
import re
import tempfile
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from langchain_core.documents import Document

from quest_rag.api.document import clean_document_text
from quest_rag.core.config import ELASTICSEARCH_URL
from quest_rag.rag.document_embedding import get_embedding
from quest_rag.rag.document_splitter import split_docs
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
from quest_rag.rag.vector_backend import ElasticsearchVectorBackend
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
JOB_SOURCE_ID = "jobs::__es_index__"


@router.post("", response_model=list[EvaluationRunSummary])
def list_runs():
    init_db()
    return list_evaluation_runs()


@router.post("/runs/get", response_model=EvaluationRunDetail)
def get_run(payload: dict):
    init_db()
    run_id = payload["run_id"]
    run = get_evaluation_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="评测记录不存在")
    return run


@router.delete("/runs/delete", response_model=CommonResponse)
def delete_run(payload: dict):
    init_db()
    run_id = payload["run_id"]
    run = delete_evaluation_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="评测记录不存在")
    ElasticsearchVectorBackend(ELASTICSEARCH_URL, run["es_index_name"]).delete_index()
    return CommonResponse(success=True, message="评测记录和历史索引已删除")


@router.post("/documents/list", response_model=list[EvaluationDocumentSummary])
def list_eval_documents():
    init_db()
    runs = list_evaluation_runs()
    return [with_latest_eval_chunk_count(with_baseline_chunk_count(doc), runs) for doc in list_evaluation_documents()]


@router.post("/documents/upload", response_model=list[EvaluationDocumentSummary])
async def upload_eval_documents(files: list[UploadFile] = File(...)):
    init_db()
    saved = []
    for file in files:
        saved.append(await save_eval_document(file))
    return [with_baseline_chunk_count(doc) for doc in saved]


@router.post("/documents/runs")
def list_eval_document_runs(payload: dict):
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
def list_eval_document_run_chunks(payload: dict):
    init_db()
    doc_id = payload["doc_id"]
    run_id = payload["run_id"]
    run = get_evaluation_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="评测记录不存在")
    if not run_includes_doc(run, doc_id):
        raise HTTPException(status_code=404, detail="该评测记录未使用此文档")
    backend = ElasticsearchVectorBackend(ELASTICSEARCH_URL, run["es_index_name"])
    return backend.list_chunks(doc_id)


@router.post("/documents/get", response_model=EvaluationDocumentDetail)
def get_eval_document(payload: dict):
    init_db()
    doc_id = payload["doc_id"]
    doc = get_evaluation_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="评测文档不存在")
    chunks = build_baseline_chunks(doc)
    return {**with_baseline_chunk_count(doc), "chunks": chunks}


@router.delete("/documents/delete", response_model=CommonResponse)
def delete_eval_document(payload: dict):
    init_db()
    doc_id = payload["doc_id"]
    if not delete_evaluation_document(doc_id):
        raise HTTPException(status_code=404, detail="评测文档不存在")
    return CommonResponse(success=True, message="评测文档已删除")


@router.post("/datasets/list")
def list_datasets():
    init_db()
    return list_evaluation_datasets()


@router.post("/datasets/import")
async def import_dataset(file: UploadFile = File(...)):
    init_db()
    content = await file.read()
    text = content.decode("utf-8-sig")
    items = parse_dataset_csv(text)
    dataset_id = f"dataset_{uuid.uuid4().hex[:12]}"
    name = Path(file.filename or "评测集").stem
    record = {"id": dataset_id, "name": name, "items": items}
    upsert_evaluation_dataset(record)
    return get_evaluation_dataset(dataset_id)


@router.post("/datasets")
def create_dataset(req: EvaluationDatasetInput):
    init_db()
    dataset_id = f"dataset_{uuid.uuid4().hex[:12]}"
    upsert_evaluation_dataset({"id": dataset_id, "name": req.name, "items": [item.model_dump() for item in req.items]})
    return get_evaluation_dataset(dataset_id)


@router.post("/datasets/get")
def get_dataset(payload: dict):
    init_db()
    dataset_id = payload["dataset_id"]
    dataset = get_evaluation_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="评测集不存在")
    return dataset


@router.put("/datasets/update")
def update_dataset(payload: dict):
    init_db()
    dataset_id = payload["dataset_id"]
    name = payload["name"]
    items = payload.get("items", [])
    if not get_evaluation_dataset(dataset_id):
        raise HTTPException(status_code=404, detail="评测集不存在")
    upsert_evaluation_dataset({"id": dataset_id, "name": name, "items": items})
    return get_evaluation_dataset(dataset_id)


@router.delete("/datasets/delete", response_model=CommonResponse)
def delete_dataset(payload: dict):
    init_db()
    dataset_id = payload["dataset_id"]
    if not delete_evaluation_dataset(dataset_id):
        raise HTTPException(status_code=404, detail="评测集不存在")
    return CommonResponse(success=True, message="评测集已删除")


@router.post("/datasets/export")
def export_dataset(payload: dict):
    init_db()
    dataset_id = payload["dataset_id"]
    dataset = get_evaluation_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="评测集不存在")
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=["ID", "用户问题", "期望答案要点", "期望来源文档ID", "期望证据文本", "是否应拒答", "评测重点", "备注"],
    )
    writer.writeheader()
    for item in dataset.get("items", []):
        writer.writerow(
            {
                "ID": item.get("id", ""),
                "用户问题": item.get("question", ""),
                "期望答案要点": item.get("expected_answer", ""),
                "期望来源文档ID": ";".join(item.get("expected_source_ids", [])),
                "期望证据文本": item.get("expected_evidence", ""),
                "是否应拒答": "是" if item.get("should_refuse") else "否",
                "评测重点": item.get("focus", ""),
                "备注": item.get("note", ""),
            }
        )
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f"attachment; filename=dataset.csv; "
                f"filename*=UTF-8''{quote(str(dataset['name']))}.csv"
            )
        },
    )


@router.post("/run", response_model=EvaluationRunDetail)
def run_evaluation(req: EvaluationRunRequest):
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
        "document_scope": {"mode": "selected" if req.document_ids else "all", "doc_ids": scope_doc_ids},
        "clean_options": req.clean_options.model_dump(),
        "split_options": req.split_options.model_dump(),
        "retrieval_options": req.retrieval_options.model_dump(),
        "summary": {},
    }
    create_evaluation_run(record)

    eval_backend = ElasticsearchVectorBackend(ELASTICSEARCH_URL, index_name)
    try:
        indexed_chunks = index_eval_documents(eval_backend, scope_doc_ids, req.clean_options, req.split_options)
        items = evaluate_items(eval_id, eval_backend, dataset.get("items", []), req.retrieval_options)
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
        backend = ElasticsearchVectorBackend(ELASTICSEARCH_URL, run["es_index_name"])
        response = backend.client.count(
            index=run["es_index_name"],
            query={"term": {"metadata.doc_id": doc_id}},
            ignore_unavailable=True,
        )
        return int(response.get("count", 0))
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


def index_eval_documents(eval_backend: ElasticsearchVectorBackend, doc_ids: list[str], clean_options, split_options) -> list[str]:
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


def parse_dataset_csv(text: str) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(text)))
    items = []
    for index, row in enumerate(rows, start=1):
        question = get_first(row, ["用户问题", "question", "问题"]) or ""
        if not question:
            continue
        items.append(
            {
                "id": get_first(row, ["ID", "id"]) or f"Q{index:04d}",
                "question": question,
                "expected_answer": get_first(row, ["期望答案要点", "expected_answer", "answer"]) or "",
                "expected_source_ids": parse_refs(get_first(row, ["期望来源文档ID", "期望来源/文档", "source_id", "sourceid"]) or ""),
                "expected_evidence": get_first(row, ["期望证据文本", "expected_evidence", "evidence"]) or "",
                "should_refuse": (get_first(row, ["是否应拒答", "should_refuse"]) or "").strip() in {"是", "true", "True", "1"},
                "focus": get_first(row, ["评测重点", "focus"]) or "",
                "note": get_first(row, ["备注", "note"]) or "",
            }
        )
    return items


def evaluate_items(eval_id: str, eval_backend: ElasticsearchVectorBackend, rows: list[dict], options) -> list[dict]:
    items = []
    for index, row in enumerate(rows, start=1):
        if not (row.get("question") or "").strip():
            continue
        expected_source_ids = row.get("expected_source_ids", [])
        query_text = row["question"]
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
        items.append(
            {
                "id": f"{eval_id}_item_{index:04d}",
                "run_id": eval_id,
                "question_id": row.get("id") or f"Q{index:04d}",
                "question": row["question"],
                "expected_answer": row.get("expected_answer"),
                "expected_source_ids": expected_source_ids,
                "expected_chunk_ids": [],
                "expected_chunk_text": row.get("expected_evidence", ""),
                "should_refuse": bool(row.get("should_refuse")),
                "retrieval_queries": retrieval_queries,
                "retrieved": retrieved,
                "metrics": metrics,
            }
        )
    return items


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
    refusal_items = [item for item in items if item["metrics"].get("should_refuse")]
    retrieval_items = [item for item in items if not item["metrics"].get("should_refuse")]
    retrieval_total = len(retrieval_items)
    refusal_total = len(refusal_items)
    source_hits = sum(1 for item in retrieval_items if item["metrics"].get("source_hit"))
    evidence_hits = sum(1 for item in retrieval_items if item["metrics"].get("evidence_hit"))
    refusal_hits = sum(1 for item in refusal_items if item["metrics"].get("refusal_hit"))
    avg_mrr = sum(float(item["metrics"].get("mrr", 0)) for item in retrieval_items) / retrieval_total if retrieval_total else 0
    pass_count = evidence_hits + refusal_hits
    return {
        "question_count": total,
        "retrieval_question_count": retrieval_total,
        "refusal_question_count": refusal_total,
        "document_count": document_count,
        "chunk_count": chunk_count,
        "source_hit_rate": round(source_hits / retrieval_total, 4) if retrieval_total else None,
        "evidence_hit_rate": round(evidence_hits / retrieval_total, 4) if retrieval_total else None,
        "refusal_hit_rate": round(refusal_hits / refusal_total, 4) if refusal_total else None,
        "pass_rate": round(pass_count / total, 4),
        "mrr": round(avg_mrr, 4),
        "miss_count": total - pass_count,
    }


def get_first(row: dict, keys: list[str]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value:
            return value
    return None


def parse_refs(value: str) -> list[str]:
    return [token.strip() for token in re.split(r"[;；,\n]", value) if token.strip()]


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
