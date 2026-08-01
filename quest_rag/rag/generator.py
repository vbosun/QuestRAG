"""
生成回复
"""
from contextvars import copy_context

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

from quest_rag.auth.schemas import CurrentUser
from quest_rag.rag.citations import get_citations, reset_citations
from quest_rag.rag.llm import llm
from quest_rag.rag.tools import tools
from quest_rag.rag.tool_registry import build_tools_for_user, current_user_ctx

SYSTEM_PROMPT = """
你是一个政务助手.帮助用户解决就业登记业务,失业登记业务问题,或者其他的可以从文档中获取到相关业务知识的问题.如果没有符合条件的资料,则拒绝回答,不要编造.
回复正文允许使用 Markdown, 用清晰的标题、列表、表格组织信息.
当工具返回了"引用编号: 【1】"这类来源编号时, 回答中的关键事实、政策条件、办理材料、岗位推荐后面要标注对应编号, 例如"应在30日内办理【1】".
只能使用工具返回过的短编号, 不要编造引用编号, 不要输出真实 source_id、chunk_id、片段位置或工具原文.
不要复述工具返回的"引用编号/来源文档/片段位置/内容"等上下文字段；这些只用于你判断答案依据.
政策、材料、流程请使用自然段、列表或表格展示，不要用代码块展示普通回答内容.
如果用户要求输出图表, 或者你的回答中确实需要用可量化数据表达图表, 必须先调用 create_chart_artifact 工具.
工具返回的图表资产 JSON 必须原样放入独立的 ```questrag-artifact 代码块中, 不要改字段名, 不要输出完整 ECharts option.
图表代码块前后继续使用 Markdown 解释图表含义. 如果没有可量化数据, 不要硬画图, 请说明无法生成图表的原因.
"""

checkpointer = InMemorySaver()


def _make_agent(current_user: CurrentUser | None = None):
    agent_tools = build_tools_for_user(current_user, tools) if current_user else tools
    return create_agent(
        model=llm, system_prompt=SYSTEM_PROMPT, tools=agent_tools, checkpointer=checkpointer
    )


def generate(question: str, thread_id: str = "1", current_user: CurrentUser | None = None) -> str:
    reset_citations()
    token = current_user_ctx.set(current_user)
    try:
        agent = _make_agent(current_user)
        result = agent.invoke(
            {"messages": [{"role": "user", "content": question}]},
            {"configurable": {"thread_id": thread_id}},
        )
        return result["messages"][-1].content
    finally:
        current_user_ctx.reset(token)


def generate_stream(question: str, thread_id: str = "1", current_user: CurrentUser | None = None):
    context = copy_context()
    iterator = context.run(_generate_stream_items, question, thread_id, current_user)
    try:
        while True:
            try:
                yield context.run(next, iterator)
            except StopIteration:
                return
    finally:
        context.run(iterator.close)


def _generate_stream_items(question: str, thread_id: str, current_user: CurrentUser | None):
    reset_citations()
    token = current_user_ctx.set(current_user)
    try:
        agent = _make_agent(current_user)
        querying = False
        for chunk in agent.stream(
            {"messages": [{"role": "user", "content": question}]},
            {"configurable": {"thread_id": thread_id}},
            stream_mode="messages",
        ):
            if is_tool_activity(chunk) and not querying:
                querying = True
                yield {"event": "status", "data": {"message": "正在查询资料中..."}}

            text = extract_stream_text(chunk)
            if text:
                if querying:
                    querying = False
                    yield {"event": "status", "data": {"message": "正在整理回答..."}}
                yield {"event": "delta", "data": {"text": text}}

        yield {"event": "sources", "data": {"sources": get_citations()}}
        yield {"event": "done", "data": {"finish_reason": "stop"}}
    finally:
        current_user_ctx.reset(token)


def is_tool_activity(chunk) -> bool:
    message = chunk[0] if isinstance(chunk, tuple) else chunk
    message_type = getattr(message, "type", None)
    if message_type == "tool":
        return True
    if getattr(message, "tool_calls", None) or getattr(message, "tool_call_chunks", None):
        return True
    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
    return bool(additional_kwargs.get("tool_calls"))


def extract_stream_text(chunk) -> str:
    message = chunk[0] if isinstance(chunk, tuple) else chunk
    message_type = getattr(message, "type", None)
    if message_type not in {"ai", "AIMessageChunk"}:
        return ""

    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def history(thread_id: str):
    agent = _make_agent()
    state_snapshot = agent.get_state({"configurable": {"thread_id": thread_id}})
    formatted_messages = [
        f"[{msg.type}]: {msg.content}" for msg in state_snapshot.values["messages"]
    ]
    return formatted_messages
