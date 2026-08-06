import pytest

from quest_rag.auth.schemas import CurrentUser
from quest_rag.auth.permission_store import _normalize_permission_codes, _normalize_rag_scope_codes
from quest_rag.rag.tool_registry import ToolPermissionError, assert_tool_permission, build_tools_for_user


class DummyTool:
    def __init__(self, name: str):
        self.name = name


def current_user(*, permissions: list[str], rag_scopes: list[str]) -> CurrentUser:
    return CurrentUser(
        id=1,
        sid="test-sid",
        role="USER",
        roles=["USER"],
        permissions=permissions,
        rag_scopes=rag_scopes,
        status=1,
        token_version=1,
    )


def test_social_security_tool_requires_permission_and_scope():
    user = current_user(
        permissions=["llm.tool.social_security_search"],
        rag_scopes=[],
    )

    tools = build_tools_for_user(user, [DummyTool("social_security_search")])

    assert tools == []


def test_job_tool_requires_jobs_scope():
    user = current_user(
        permissions=["llm.tool.job_search"],
        rag_scopes=["public_policy"],
    )

    tools = build_tools_for_user(user, [DummyTool("retrieve_jobs")])

    assert tools == []


def test_tool_scope_is_enforced_at_execution(monkeypatch):
    monkeypatch.setattr(
        "quest_rag.auth.permission_store.insert_llm_tool_call_log",
        lambda **kwargs: None,
    )
    user = current_user(
        permissions=["llm.tool.social_security_search"],
        rag_scopes=[],
    )

    with pytest.raises(ToolPermissionError, match="缺少数据范围"):
        assert_tool_permission(user, "social_security_search")


def test_tool_is_available_when_permission_and_scope_match():
    user = current_user(
        permissions=["llm.tool.social_security_search"],
        rag_scopes=["social_security_mock"],
    )

    tools = build_tools_for_user(user, [DummyTool("social_security_search")])

    assert [tool.name for tool in tools] == ["social_security_search"]


def test_child_permissions_are_dropped_without_parent_page_permission():
    normalized = _normalize_permission_codes(
        ["evaluation.run.create", "chat.view"],
        {"evaluation.run.create", "evaluation.view", "chat.view"},
    )

    assert normalized == ["chat.view"]


def test_scope_selection_requires_related_tool_permission():
    normalized = _normalize_rag_scope_codes(
        ["public_policy", "jobs", "social_security_mock"],
        {"llm.tool.knowledge_search"},
    )

    assert normalized == ["public_policy"]
