from datetime import datetime

from pydantic import BaseModel


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

class DocumentInfo(BaseModel):
    id: str                     # 文档的唯一标识（如文件名或UUID）
    source: str                 # 原始文件路径或名称
    chunk_count: int            # 切分后的块数
    uploaded_at: datetime       # 上传时间

class UploadResponse(BaseModel):
    success: bool
    doc_id: str
    chunk_count: int
    message: str

class DocumentListResponse(BaseModel):
    total: int
    documents: list[DocumentInfo]


class DocMetadata(BaseModel):
    doc_id: str
    filename: str
    chunk_count: int
    uploaded_at: datetime
