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
    name: str = Field(
        default="",
        description="数据项名称，显示在分类轴标签、图例或扇区名称中",
    )
    value: float | None = Field(
        default=None,
        description="数据项的主数值，用于饼图/柱状图/折线图/漏斗图/雷达图",
    )
    x: float | None = Field(
        default=None,
        description="散点图/气泡图的 X 轴数值坐标，仅 chart_type=scatter/bubble 时使用",
    )
    y: float | None = Field(
        default=None,
        description="散点图/气泡图的 Y 轴数值坐标，仅 chart_type=scatter/bubble 时使用",
    )
    size: float | None = Field(
        default=None,
        description="气泡图的气泡大小，仅 chart_type=bubble 时使用",
    )
    series: str | None = Field(
        default=None,
        description="数据分组/系列名，用于区分柱状图的分组柱、折线图的多条线、散点图的多个系列",
    )


class ChartArtifact(BaseModel):
    type: Literal["chart"] = "chart"
    version: str = "1.0"
    id: str
    chart_type: Literal["pie", "line", "bar", "scatter", "radar", "funnel", "heatmap", "bubble"]
    title: str
    description: str | None = None
    data: list[ChartDatum]
    encoding: dict
    download: dict
    source_note: str | None = None


class ChartToolInput(BaseModel):
    chart_type: Literal["pie", "line", "bar", "scatter", "radar", "funnel", "heatmap", "bubble"] = Field(
        description=(
            "图表类型：pie=饼图（占比/构成），line=折线图（趋势/变化），"
            "bar=柱状图（对比/排名），scatter=散点图（相关性/分布），"
            "radar=雷达图（多维对比），funnel=漏斗图（转化/层级），"
            "heatmap=热力图（交叉强度），bubble=气泡图（三维散点）"
        ),
    )
    title: str = Field(
        min_length=1,
        max_length=80,
        description="图表标题，不超过 80 字",
    )
    data: list[ChartDatum] = Field(
        min_length=1,
        max_length=50,
        description=(
            "图表数据，每条为一个 ChartDatum。按图表类型填写对应字段：\n"
            "- pie/funnel：每项填 name + value\n"
            "- line/bar/radar：每项填 name + value，多个系列用 series 区分\n"
            "- heatmap：每项填 name(横轴) + series(纵轴) + value(强度)\n"
            "- scatter：每项填 x + y，多个系列用 series 区分\n"
            "- bubble：每项填 x + y + size，多个系列用 series 区分"
        ),
    )
    description: str | None = Field(
        default=None,
        max_length=300,
        description="图表补充说明，不超过 300 字",
    )
    x_field: str = Field(
        default="name",
        description="X 轴/分类轴在 data 中对应的字段名，默认 'name'",
    )
    y_field: str = Field(
        default="value",
        description="Y 轴/数值轴在 data 中对应的字段名，默认 'value'",
    )
    series_field: str | None = Field(
        default=None,
        description="分组/系列在 data 中对应的字段名，有多个系列时指定，默认 'series'",
    )
    source_note: str | None = Field(
        default=None,
        max_length=300,
        description="数据来源说明，不超过 300 字",
    )


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
    scope_code: str = Field(default="public_policy", max_length=64)
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
    strategy: Literal["fixed", "structure", "recursive"] = "fixed"
    separator_preset: Literal["general", "chinese", "english"] = "general"


class RetrievalOptions(BaseModel):
    top_k: int = Field(default=5, ge=1, le=20)
    recall_k: int = Field(default=15, ge=1, le=50)
    mode: Literal["hybrid", "vector", "keyword"] = "hybrid"
    rrf_k: int = Field(default=60, ge=1, le=120)


class GenerationOptions(BaseModel):
    model: str | None = Field(default=None, max_length=80)
    temperature: float = Field(default=0.1, ge=0, le=2)
    top_p: float = Field(default=1.0, ge=0.01, le=1)
    max_tokens: int = Field(default=4000, ge=256, le=25000)
    system_prompt_version: str = Field(default="default", max_length=80)
    tool_policy: Literal["current_user"] = "current_user"
    seed: int | None = Field(default=None, ge=0)


class RagasOptions(BaseModel):
    enabled: bool = True
    metrics: list[Literal[
        "faithfulness",
        "factual_correctness",
        "response_relevancy",
        "context_precision",
        "context_recall",
    ]] = Field(default_factory=lambda: [
        "faithfulness",
        "factual_correctness",
        "response_relevancy",
        "context_precision",
        "context_recall",
    ])


class EvaluationRunRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    dataset_id: str = Field(min_length=1)
    document_ids: list[str] = Field(default_factory=list)
    evaluation_mode: Literal["retrieval", "generation", "both"] = "both"
    clean_options: CleanOptions = Field(default_factory=CleanOptions)
    split_options: SplitOptions = Field(default_factory=SplitOptions)
    retrieval_options: RetrievalOptions = Field(default_factory=RetrievalOptions)
    generation_options: GenerationOptions = Field(default_factory=GenerationOptions)
    ragas_options: RagasOptions = Field(default_factory=RagasOptions)


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
    retrieval_index_name: str | None = None
    evaluation_mode: str = "retrieval"
    document_scope: dict
    clean_options: dict
    split_options: dict
    retrieval_options: dict
    generation_options: dict = Field(default_factory=dict)
    ragas_options: dict = Field(default_factory=dict)
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

class DocumentStatsResponse(BaseModel):
    document_count: int
    total_chunks: int
    total_text_length: int
    total_token_count: int
    max_text_length: int
    min_text_length: int
    format_distribution: dict[str, int]


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
    token_count: int = 0
    scope_code: str = "public_policy"
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
