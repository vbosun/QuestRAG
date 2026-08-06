"""
生成回复
"""
from contextvars import copy_context

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

from quest_rag.auth.schemas import CurrentUser
from quest_rag.rag.citations import get_citations, reset_citations
from quest_rag.rag.llm import llm, make_llm
from quest_rag.rag.trace import current_eval_backend_ctx, current_eval_retrieval_options_ctx, current_trace_ctx
from quest_rag.rag.tools import tools
from quest_rag.rag.tool_registry import build_tools_for_user, current_conversation_ctx, current_user_ctx

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
当用户询问本人社保、缴费记录、养老/医保账户时，应调用 social_security_search 工具，不要编造社保数据.
当用户询问补贴资格、可享受哪些补贴或补贴金额时，应先调用 subsidy_match 或 subsidy_calculate 工具，不要直接根据政策文本猜测金额.
如果 subsidy_match/subsidy_calculate 返回缺失信息，应先追问用户补充关键信息，不要强行测算.
补贴金额、是否符合、计算过程必须以 subsidy_calculate 的结果为准.
政策依据、办理材料、办理流程可结合 retrieve_context 的引用编号说明.
补贴测算结果仅供参考，最终以当地经办机构审核为准.
"""

checkpointer = InMemorySaver()


def _make_agent(current_user: CurrentUser | None = None, generation_options: dict | None = None):
    agent_tools = build_tools_for_user(current_user, tools) if current_user else tools
    model = llm
    if generation_options:
        model = make_llm(
            model=generation_options.get("model") or None,
            temperature=float(generation_options.get("temperature", 0.5)),
            top_p=float(generation_options["top_p"]) if generation_options.get("top_p") is not None else None,
            max_tokens=int(generation_options.get("max_tokens") or 25000),
        )
    return create_agent(
        model=model, system_prompt=SYSTEM_PROMPT, tools=agent_tools, checkpointer=checkpointer
    )


def generate(
    question: str,
    thread_id: str = "1",
    current_user: CurrentUser | None = None,
    memory_context: str | None = None,
    generation_options: dict | None = None,
) -> str:
    reset_citations()
    token = current_user_ctx.set(current_user)
    conversation_token = current_conversation_ctx.set(thread_id)
    try:
        agent = _make_agent(current_user, generation_options)
        result = agent.invoke(
            {"messages": [{"role": "user", "content": build_question_with_memory(question, memory_context)}]},
            {"configurable": {"thread_id": thread_id}},
        )
        return result["messages"][-1].content
    finally:
        current_conversation_ctx.reset(conversation_token)
        current_user_ctx.reset(token)


def generate_with_trace(
    question: str,
    thread_id: str = "1",
    current_user: CurrentUser | None = None,
    memory_context: str | None = None,
    generation_options: dict | None = None,
    eval_backend=None,
    retrieval_options: dict | None = None,
) -> dict:
    trace: list[dict] = []
    reset_citations()
    token = current_user_ctx.set(current_user)
    conversation_token = current_conversation_ctx.set(thread_id)
    trace_token = current_trace_ctx.set(trace)
    backend_token = current_eval_backend_ctx.set(eval_backend)
    retrieval_token = current_eval_retrieval_options_ctx.set(retrieval_options)
    try:
        agent = _make_agent(current_user, generation_options)
        result = agent.invoke(
            {"messages": [{"role": "user", "content": build_question_with_memory(question, memory_context)}]},
            {"configurable": {"thread_id": thread_id}},
        )
        return {
            "answer": result["messages"][-1].content,
            "tool_calls": trace,
            "citations": get_citations(),
        }
    finally:
        current_eval_retrieval_options_ctx.reset(retrieval_token)
        current_eval_backend_ctx.reset(backend_token)
        current_trace_ctx.reset(trace_token)
        current_conversation_ctx.reset(conversation_token)
        current_user_ctx.reset(token)


def generate_stream(
    question: str,
    thread_id: str = "1",
    current_user: CurrentUser | None = None,
    memory_context: str | None = None,
    generation_options: dict | None = None,
):
    context = copy_context()
    iterator = context.run(_generate_stream_items, question, thread_id, current_user, memory_context, generation_options)
    try:
        while True:
            try:
                yield context.run(next, iterator)
            except StopIteration:
                return
    finally:
        context.run(iterator.close)


def _generate_stream_items(
    question: str,
    thread_id: str,
    current_user: CurrentUser | None,
    memory_context: str | None,
    generation_options: dict | None,
):
    reset_citations()
    token = current_user_ctx.set(current_user)
    conversation_token = current_conversation_ctx.set(thread_id)
    try:
        agent = _make_agent(current_user, generation_options)
        querying = False
        for chunk in agent.stream(
            {"messages": [{"role": "user", "content": build_question_with_memory(question, memory_context)}]},
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
        current_conversation_ctx.reset(conversation_token)
        current_user_ctx.reset(token)


def build_question_with_memory(question: str, memory_context: str | None) -> str:
    if not memory_context:
        return question
    return (
        "以下是当前会话已保存的上下文和工具事实，只能作为本轮理解上下文使用；"
        "涉及资格和金额时仍需按工具规则判断，不要编造。\n\n"
        f"{memory_context}\n\n"
        f"用户本轮问题：{question}"
    )


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
