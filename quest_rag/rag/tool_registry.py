"""
工具注册表：为每个工具声明所需权限和风险级别。

Agent 构造工具列表时按用户权限过滤，HIGH/CRITICAL 默认不注册。
工具执行入口也做二次校验。
"""
from contextvars import ContextVar

from quest_rag.auth.schemas import CurrentUser

# 工具执行时通过 contextvar 获取当前用户
current_user_ctx: ContextVar[CurrentUser | None] = ContextVar("current_user", default=None)
current_conversation_ctx: ContextVar[str | None] = ContextVar("current_conversation", default=None)


TOOL_REGISTRY: dict[str, dict] = {
    "retrieve_context": {
        "permission": "llm.tool.knowledge_search",
        "risk_level": "LOW",
        "mode": "read",
    },
    "get_document_list": {
        "permission": "llm.tool.knowledge_search",
        "risk_level": "LOW",
        "mode": "read",
    },
    "retrieve_jobs": {
        "permission": "llm.tool.job_search",
        "risk_level": "LOW",
        "mode": "read",
    },
    "create_chart_artifact": {
        "permission": "llm.tool.knowledge_search",
        "risk_level": "LOW",
        "mode": "read",
    },
    "social_security_search": {
        "permission": "llm.tool.social_security_search",
        "risk_level": "LOW",
        "mode": "read",
    },
    "subsidy_match": {
        "permission": "llm.tool.subsidy_match",
        "risk_level": "LOW",
        "mode": "read",
    },
    "subsidy_calculate": {
        "permission": "llm.tool.subsidy_calculate",
        "risk_level": "LOW",
        "mode": "read",
    },
}

# 第一阶段不注册给 Agent 的高风险工具
RESTRICTED_TOOLS: dict[str, dict] = {}


class ToolPermissionError(Exception):
    def __init__(self, tool_name: str, reason: str):
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"工具 '{tool_name}' 权限不足: {reason}")


def build_tools_for_user(current_user: CurrentUser, tools: list):
    """按用户权限过滤工具列表，并排除 HIGH/CRITICAL 工具。"""
    allowed = []
    for tool in tools:
        tool_name = getattr(tool, "name", str(tool))
        spec = TOOL_REGISTRY.get(tool_name)
        if spec is None:
            continue  # 未注册的工具默认拒绝
        permission = spec.get("permission")
        if not permission:
            continue
        if permission not in current_user.permissions:
            continue
        if spec.get("risk_level") in {"HIGH", "CRITICAL"}:
            continue
        allowed.append(tool)
    return allowed


def assert_tool_permission(current_user: CurrentUser, tool_name: str):
    """工具执行前的二次校验。"""
    spec = TOOL_REGISTRY.get(tool_name)
    if spec is None:
        raise ToolPermissionError(tool_name, "未注册")

    permission = spec.get("permission")
    if not permission:
        raise ToolPermissionError(tool_name, "无权限声明")

    if permission not in current_user.permissions:
        from quest_rag.auth.permission_store import insert_llm_tool_call_log

        insert_llm_tool_call_log(
            user_id=current_user.id,
            tool_name=tool_name,
            permission_code=permission,
            allowed=False,
            deny_reason="missing_permission",
        )
        raise ToolPermissionError(tool_name, "缺少权限")

    from quest_rag.auth.permission_store import insert_llm_tool_call_log

    insert_llm_tool_call_log(
        user_id=current_user.id,
        session_id=current_user.sid,
        tool_name=tool_name,
        permission_code=permission,
        allowed=True,
        effective_scopes=current_user.rag_scopes,
    )
