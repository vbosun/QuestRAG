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
