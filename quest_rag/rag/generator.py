"""
生成回复
"""
from contextvars import copy_context

from langchain.agents import create_agent

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
当用户询问能办什么业务时，先调用 list_available_applications；询问办理条件、流程、材料或表单时，调用 get_application_guidance；询问本人是否满足条件时，调用 assess_application_eligibility，不得主观判断。当前有 employment_registration（就业登记申请）和 unemployment_registration（失业登记申请）。失业登记核验时，用户明确说“未就业/失业”应传 is_unemployed=true，不要把它当成 has_started_employment=false 的就业登记核验。
发起申请前，先用 assess_application_eligibility 核验基础条件；若返回 needs_information，追问缺失信息；若返回 not_eligible，说明原因且不要创建草稿；仅返回 eligible 时调用 start_application 创建草稿。若用户在当前对话明确提供了联系电话或就业类型，必须将原值分别传给 start_application 的 phone 和 employment_type 参数（“单位就业”可直接传中文，工具会规范化），不要丢弃。创建草稿不等于提交申请。用户询问已创建申请进度时，可调用 get_application_status；这些工具不能打开网页、填写、上传或提交。
当 start_application 工具返回 ```questrag-artifact 区块时，必须在最终回复中原样保留该区块，不能改写或省略；前端会据此自动弹出可编辑表单。
当用户表达“我要办理就业登记”“我要申请就业登记”“帮我做就业登记”或要求打开就业登记表单时，先调用 assess_application_eligibility(business_code="employment_registration")；条件满足后再调用 start_application，不要只讲解流程或让用户前往其他页面。
当用户询问当前已嵌入申请页面的字段、填写值、校验或下一步时，调用 get_application_form(case_id) 读取已接入业务页面的结构化状态。不要笼统回复“无法看到浏览器页面”：应说明你可以读取当前已接入申请页面的数据，但不能读取用户未接入的任意屏幕或其他网页；不要声称拥有通用屏幕视觉能力。
只有用户明确要求“帮我填写/代填/把 X 填成 Y”时，才调用 update_application_form_field(case_id, field_key, value) 填写一个明确字段；不得根据推测自动修改字段。调用后告诉用户已填写并请其核对，最终提交仍由用户操作。
当管理员要接入新的业务网页时，使用 analyze_business_page(url) 读取页面表单结构；向管理员展示识别出的字段和不确定项，待其确认或提供修正映射后，再调用 save_business_page_config 保存。不要在未确认映射时发布配置。可用 list_business_page_configs 查询已接入业务页面。
"""

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
    # Conversation history is persisted in chat_memory and passed into each turn as text.
    # A process-local LangGraph checkpoint duplicates that state and can retain an incomplete
    # provider tool_call after an interrupted stream. Reusing it then violates the OpenAI tool
    # message protocol (every tool_call must have a matching tool result).
    return create_agent(model=model, system_prompt=SYSTEM_PROMPT, tools=agent_tools)


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
    # The canonical conversation history is in chat_memory.store; do not reconstruct it
    # from an ephemeral agent checkpoint.
    return []
