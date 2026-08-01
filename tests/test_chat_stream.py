import json
import re

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk, ToolMessage

from quest_rag.main import app
from quest_rag.rag.citations import get_citations, reset_citations
from quest_rag.rag.generator import extract_stream_text, is_tool_activity
from quest_rag.rag.tools import create_chart_artifact
from quest_rag.rag.tools import format_job_result


def test_chat_stream_sse_events(monkeypatch):
    def fake_generate_stream(question: str, thread_id: str):
        assert question == "测试"
        assert thread_id == "session-1"
        yield {"event": "delta", "data": {"text": "你好"}}
        yield {"event": "done", "data": {"finish_reason": "stop"}}

    monkeypatch.setattr("quest_rag.api.chat.generate_stream", fake_generate_stream)

    from quest_rag.auth.dependencies import get_current_user
    from quest_rag.auth.schemas import CurrentUser

    async def fake_get_current_user():
        return CurrentUser(id=1, sid="test-sid", role="ADMIN", status=1, full_name="测试", id_number_masked="1101**********001", token_version=1)

    app.dependency_overrides[get_current_user] = fake_get_current_user

    client = TestClient(app)

    try:
        with client.stream(
            "POST",
            "/chat/stream",
            json={
                "message": "测试",
                "session_id": "session-1",
                "history": [],
                "stream": True,
            },
        ) as response:
            body = "".join(response.iter_text())

        assert response.status_code == 200
        assert "event: meta" in body
        assert 'data: {"session_id": "session-1"}' in body
        assert "event: delta" in body
        assert 'data: {"text": "你好"}' in body
        assert "event: done" in body
    finally:
        app.dependency_overrides.clear()


def test_create_chart_artifact_returns_stable_json_payload():
    result = create_chart_artifact.invoke(
        {
            "chart_type": "pie",
            "title": "问题类型占比",
            "data": [
                {"name": "办理条件", "value": 42},
                {"name": "办理材料", "value": 31},
            ],
        }
    )

    match = re.search(r"(\{.*\})$", result)
    assert match
    payload = json.loads(match.group(1))
    assert payload["type"] == "chart"
    assert payload["chart_type"] == "pie"
    assert payload["encoding"] == {"x": "name", "y": "value", "series": None}
    assert payload["download"]["filename"] == "问题类型占比.png"
    assert payload["data"][0]["value"] == 42


def test_extract_stream_text_filters_tool_messages():
    tool_message = ToolMessage(
        content="引用编号: 【1】\n来源文档: 测试.txt\n内容: 工具上下文不应流给前端",
        tool_call_id="tool-1",
    )
    ai_message = AIMessageChunk(content="最终回答【1】")

    assert extract_stream_text(tool_message) == ""
    assert extract_stream_text(ai_message) == "最终回答【1】"
    assert is_tool_activity(tool_message)


def test_tool_citations_are_available_after_tool_call():
    reset_citations()
    result = format_job_result(
        {
            "id": "job-1",
            "title": "测试岗位",
            "company": "测试单位",
            "address": "兰州",
            "salary": "3000-5000元",
            "score": 0.8,
        }
    )

    citations = get_citations()
    assert "引用编号: 【1】" in result
    assert len(citations) == 1
    assert citations[0]["label"] == "1"
    assert citations[0]["ref_id"] == "job-1"
