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

class DocInfo(BaseModel):
    id: str


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
