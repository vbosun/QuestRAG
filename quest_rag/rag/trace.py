from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from quest_rag.rag.vector_backend import VectorBackend


current_trace_ctx: ContextVar[list[dict[str, Any]] | None] = ContextVar("current_trace", default=None)
current_eval_backend_ctx: ContextVar[VectorBackend | None] = ContextVar("current_eval_backend", default=None)
current_eval_retrieval_options_ctx: ContextVar[dict[str, Any] | None] = ContextVar("current_eval_retrieval_options", default=None)


def append_tool_trace(event: dict[str, Any]) -> None:
    trace = current_trace_ctx.get()
    if trace is not None:
        trace.append(event)


def trace_contexts() -> list[str]:
    contexts: list[str] = []
    for event in current_trace_ctx.get() or []:
        for context in event.get("contexts", []) or []:
            text = context.get("text") if isinstance(context, dict) else None
            if isinstance(text, str) and text.strip():
                contexts.append(text)
    return contexts
