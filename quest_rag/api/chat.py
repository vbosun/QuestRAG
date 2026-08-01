import json
import uuid
from inspect import signature

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from quest_rag.logger import logger

from quest_rag.auth.dependencies import require_permission
from quest_rag.auth.schemas import CurrentUser
from quest_rag.chat_memory.store import (
    create_conversation,
    delete_conversation,
    ensure_conversation,
    get_conversation_detail,
    insert_message,
    list_conversations,
    load_memory_context,
    rename_conversation,
)
from quest_rag.rag.generator import generate, generate_stream, history
from quest_rag.schemas.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["CHAT"])


class ConversationListRequest(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=30, ge=1, le=100)


class ConversationCreateRequest(BaseModel):
    title: str = Field(default="新会话", max_length=160)


class ConversationIdRequest(BaseModel):
    conversation_id: str


class ConversationRenameRequest(BaseModel):
    conversation_id: str
    title: str = Field(min_length=1, max_length=160)


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, current_user: CurrentUser = Depends(require_permission("chat.view"))):
    """接收问题，返回回答"""
    conversation = ensure_conversation(current_user.id, req.session_id, req.message[:24] or "新会话")
    session_id = conversation["id"]
    memory_context = load_memory_context(current_user.id, session_id)
    insert_message(current_user.id, session_id, "user", req.message)

    try:
        result = generate(
            question=req.message,
            thread_id=session_id,
            current_user=current_user,
            memory_context=memory_context,
        )
        insert_message(current_user.id, session_id, "assistant", result, raw=result)
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
def chat_stream(req: ChatRequest, current_user: CurrentUser = Depends(require_permission("chat.view"))):
    """接收问题，使用 SSE 流式返回回答"""
    conversation = ensure_conversation(current_user.id, req.session_id, req.message[:24] or "新会话")
    session_id = conversation["id"]
    memory_context = load_memory_context(current_user.id, session_id)
    insert_message(current_user.id, session_id, "user", req.message)

    def event_stream():
        yield encode_sse("meta", {"session_id": session_id})
        assistant_raw = []
        citations = []
        error_message = None
        try:
            for item in call_generate_stream(req.message, session_id, current_user, memory_context):
                if item["event"] == "delta":
                    assistant_raw.append(item["data"].get("text", ""))
                if item["event"] == "sources":
                    citations = item["data"].get("sources", [])
                yield encode_sse(item["event"], item["data"])
        except Exception as e:
            logger.exception(str(e))
            error_message = "模型服务连接失败，请确认本地 Ollama/OpenAI 兼容服务已启动，且 OPENAI_BASE_URL 配置正确。"
            yield encode_sse(
                "error",
                {
                    "message": error_message
                },
            )
            yield encode_sse("done", {"finish_reason": "error"})
        finally:
            raw = "".join(assistant_raw)
            if raw or error_message:
                insert_message(
                    current_user.id,
                    session_id,
                    "assistant",
                    raw,
                    raw=raw,
                    parts=[{"type": "markdown", "content": raw}] if raw else [],
                    citations=citations,
                    status="failed" if error_message else "completed",
                    error=error_message,
                )

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


def call_generate_stream(question: str, session_id: str, current_user: CurrentUser, memory_context: str | None):
    params = signature(generate_stream).parameters
    if "memory_context" in params:
        return generate_stream(
            question=question,
            thread_id=session_id,
            current_user=current_user,
            memory_context=memory_context,
        )
    return generate_stream(question=question, thread_id=session_id, current_user=current_user)

@router.post("/history", response_model=list[str])
def chat_history(req: ChatRequest, current_user: CurrentUser = Depends(require_permission("chat.view"))):
    """获取对话历历史"""
    session_id = req.session_id or str(uuid.uuid4())
    return history(session_id)


@router.post("/conversations/list")
def conversation_list(
    req: ConversationListRequest,
    current_user: CurrentUser = Depends(require_permission("chat.view")),
):
    return list_conversations(current_user.id, req.page, req.page_size)


@router.post("/conversations/create")
def conversation_create(
    req: ConversationCreateRequest,
    current_user: CurrentUser = Depends(require_permission("chat.view")),
):
    conversation = create_conversation(current_user.id, req.title)
    conversation["messages"] = []
    conversation["tool_memories"] = []
    return conversation


@router.post("/conversations/get")
def conversation_get(
    req: ConversationIdRequest,
    current_user: CurrentUser = Depends(require_permission("chat.view")),
):
    detail = get_conversation_detail(current_user.id, req.conversation_id)
    if not detail:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "会话不存在"})
    return detail


@router.post("/conversations/delete")
def conversation_delete(
    req: ConversationIdRequest,
    current_user: CurrentUser = Depends(require_permission("chat.view")),
):
    return {"success": delete_conversation(current_user.id, req.conversation_id)}


@router.post("/conversations/rename")
def conversation_rename(
    req: ConversationRenameRequest,
    current_user: CurrentUser = Depends(require_permission("chat.view")),
):
    row = rename_conversation(current_user.id, req.conversation_id, req.title)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "会话不存在"})
    return row
