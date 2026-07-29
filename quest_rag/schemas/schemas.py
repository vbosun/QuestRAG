from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CommonResponse(BaseModel):
    success: bool
    message: str|None

class ChatRequest(BaseModel):
    message: str
    session_id: str|None
    history: list[dict] | None
    temperature: float = 0.7
    stream: bool = False

class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[dict] | None


class ChartDatum(BaseModel):
    name: str
    value: float
    series: str | None = None


class ChartArtifact(BaseModel):
    type: Literal["chart"] = "chart"
    version: str = "1.0"
    id: str
    chart_type: Literal["pie", "line", "bar"]
    title: str
    description: str | None = None
    data: list[ChartDatum]
    encoding: dict
    download: dict
    source_note: str | None = None


class ChartToolInput(BaseModel):
    chart_type: Literal["pie", "line", "bar"]
    title: str = Field(min_length=1, max_length=80)
    data: list[ChartDatum] = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=300)
    x_field: str = "name"
    y_field: str = "value"
    series_field: str | None = None
    source_note: str | None = Field(default=None, max_length=300)


class JobSearchToolInput(BaseModel):
    query: str = Field(min_length=1, description="岗位检索条件，例如岗位名称、城市、薪资、学历、经验等")
    top_k: int = Field(default=10, ge=1, le=10, description="最多返回的岗位数量，不能超过 10")

class UploadResponse(BaseModel):
    success: bool
    doc_id: str
    chunk_count: int
    message: str


class DocumentMetadataInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    category: str = Field(default="policy", max_length=40)
    organization: str | None = Field(default=None, max_length=120)
    publish_date: str | None = Field(default=None, max_length=40)
    region: str | None = Field(default=None, max_length=80)
    keywords: list[str] = Field(default_factory=list, max_length=20)
    notes: str | None = Field(default=None, max_length=500)


class CleanOptions(BaseModel):
    trim_lines: bool = True
    normalize_spaces: bool = True
    merge_blank_lines: bool = True
    merge_broken_lines: bool = False


class SplitOptions(BaseModel):
    chunk_size: int = Field(default=500, ge=50, le=3000)
    chunk_overlap: int = Field(default=100, ge=0, le=1000)
    attach_title: bool = True


class RetrievalOptions(BaseModel):
    top_k: int = Field(default=5, ge=1, le=20)
    mode: Literal["hybrid", "vector", "keyword"] = "hybrid"
    score_threshold: float = Field(default=0.0, ge=0, le=2)
    vector_weight: float = Field(default=0.6, ge=0, le=1)
    keyword_weight: float = Field(default=0.4, ge=0, le=1)


class EvaluationRunRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    dataset_id: str = Field(min_length=1)
    document_ids: list[str] = Field(default_factory=list)
    clean_options: CleanOptions = Field(default_factory=CleanOptions)
    split_options: SplitOptions = Field(default_factory=SplitOptions)
    retrieval_options: RetrievalOptions = Field(default_factory=RetrievalOptions)


class EvaluationDocumentSummary(BaseModel):
    id: str
    filename: str
    title: str
    file_type: str
    file_size: int
    metadata: dict
    chunk_count: int = 0
    latest_eval_run_id: str | None = None
    latest_eval_run_name: str | None = None
    latest_eval_chunk_count: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EvaluationDocumentDetail(EvaluationDocumentSummary):
    chunks: list[dict] = Field(default_factory=list)


class EvaluationDatasetItem(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    question: str = ""
    expected_answer: str | None = None
    expected_source_ids: list[str] = Field(default_factory=list)
    expected_evidence: str | None = None
    should_refuse: bool = False
    focus: str | None = None
    note: str | None = None


class EvaluationDatasetInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    items: list[EvaluationDatasetItem] = Field(default_factory=list)


class EvaluationRunSummary(BaseModel):
    id: str
    name: str
    status: str
    dataset_path: str
    es_index_name: str
    document_scope: dict
    clean_options: dict
    split_options: dict
    retrieval_options: dict
    summary: dict
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class EvaluationRunDetail(EvaluationRunSummary):
    items: list[dict] = Field(default_factory=list)


class DocumentStageResponse(BaseModel):
    stage_id: str
    filename: str
    file_type: str
    file_size: int
    page_count: int
    metadata: DocumentMetadataInput
    clean_options: CleanOptions
    split_options: SplitOptions
    raw_preview: str
    cleaned_preview: str
    chunk_count: int
    chunk_preview: list[dict]


class DocumentStageRequest(BaseModel):
    stage_id: str
    metadata: DocumentMetadataInput
    clean_options: CleanOptions
    split_options: SplitOptions
    replace_doc_id: str | None = None


class DocumentCommitResponse(BaseModel):
    success: bool
    doc_id: str
    chunk_count: int
    message: str

class DocInfo(BaseModel):
    id: str


class DocumentChunk(BaseModel):
    chunk_id: str
    text: str
    metadata: dict
    length: int


class DocMetadata(BaseModel):
    doc_id: str
    filename: str
    chunk_count: int
    uploaded_at: datetime

class ValidationResult(BaseModel):
    passed: bool = Field(
        description="回答是否通过校验"
    )

    score: int = Field(
        description="可信度评分 0-100"
    )

    reason: str = Field(
        description="校验原因"
    )

    unsupported_content: list[str] = Field(
        default=[],
        description="无法被资料支持的内容"
    )
