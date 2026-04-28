import uuid

from fastapi import APIRouter

from quest_rag.rag.generator import generate, history
from quest_rag.schemas.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["CHAT"])

@router.post("/chat", response_model=ChatResponse)
def chat(req:ChatRequest):
    """接收问题，返回回答"""
    session_id = req.session_id or str(uuid.uuid4())

    result = generate(
        question=req.message,
        thread_id=session_id
    )

    return ChatResponse(
        session_id=session_id,
        answer= result,
        sources=None
    )

@router.post("/history", response_model=list[str])
def chat_history(req:ChatRequest):
    """获取对话历历史"""
    session_id = req.session_id or str(uuid.uuid4())
    return history(session_id)




