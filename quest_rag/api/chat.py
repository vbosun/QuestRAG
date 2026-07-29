import json
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from logger import logger

from quest_rag.rag.generator import generate, generate_stream, history
from quest_rag.schemas.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["CHAT"])

@router.post("/chat", response_model=ChatResponse)
def chat(req:ChatRequest):
    """接收问题，返回回答"""
    session_id = req.session_id or str(uuid.uuid4())

    try:
        result = generate(
            question=req.message,
            thread_id=session_id
        )
    except Exception as e:
        logger.exception(str(e))
        raise HTTPException(
            status_code=502,
            detail="模型服务连接失败，请确认本地 Ollama/OpenAI 兼容服务已启动，且 OPENAI_BASE_URL 配置正确。",
        ) from e

    return ChatResponse(
        session_id=session_id,
        answer= result,
        sources=None
    )


@router.post("/stream")
def chat_stream(req: ChatRequest):
    """接收问题，使用 SSE 流式返回回答"""
    session_id = req.session_id or str(uuid.uuid4())

    def event_stream():
        yield encode_sse("meta", {"session_id": session_id})
        try:
            for item in generate_stream(
                question=req.message,
                thread_id=session_id,
            ):
                yield encode_sse(item["event"], item["data"])
        except Exception as e:
            logger.exception(str(e))
            yield encode_sse(
                "error",
                {
                    "message": "模型服务连接失败，请确认本地 Ollama/OpenAI 兼容服务已启动，且 OPENAI_BASE_URL 配置正确。"
                },
            )
            yield encode_sse("done", {"finish_reason": "error"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def encode_sse(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"

@router.post("/history", response_model=list[str])
def chat_history(req:ChatRequest):
    """获取对话历历史"""
    session_id = req.session_id or str(uuid.uuid4())
    return history(session_id)




