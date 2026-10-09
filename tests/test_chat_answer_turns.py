import json

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langchain_core.tools import tool

from quest_rag.rag import generator


class ToolStreamingModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        message = self._generate(messages).generations[0].message
        # Reproduce the provider's problematic ordering: text arrives BEFORE calls.
        for text in (message.content[:5], message.content[5:]):
            yield ChatGenerationChunk(message=AIMessageChunk(content=text))
        for index, call in enumerate(message.tool_calls):
            yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=[{
                "name": call["name"], "args": json.dumps(call["args"]),
                "id": call["id"], "index": index,
            }]))
        yield ChatGenerationChunk(message=AIMessageChunk(content="", chunk_position="last"))


def install_agent(monkeypatch, responses):
    @tool
    def lookup_policy() -> str:
        """Look up the relevant policy."""
        return "工具检索原文：测试政策，不应直接展示。"

    model = ToolStreamingModel(responses=responses)
    agent = create_agent(model=model, tools=[lookup_policy])
    monkeypatch.setattr(generator, "_make_agent", lambda *args: agent)


def tool_turn(text, call_id):
    return AIMessage(content=text, tool_calls=[{
        "name": "lookup_policy", "args": {}, "id": call_id,
    }])


def test_only_final_answer_is_published_after_multiple_tool_rounds(monkeypatch):
    final = "## 补贴政策\n\n依据测试政策【1】。\n\n```questrag-artifact\n{}\n```"
    install_agent(monkeypatch, [
        tool_turn("I'll look into the subsidy policies.", "call-1"),
        tool_turn("我会继续核对政策。", "call-2"),
        AIMessage(content=final),
    ])
    events = list(generator.generate_stream("有哪些政策？"))
    assert "".join(item["data"]["text"] for item in events if item["event"] == "delta") == final
    assert any(item["event"] == "status" and "查询" in item["data"]["message"] for item in events)
    assert [item["event"] for item in events[-2:]] == ["sources", "done"]


@pytest.mark.parametrize("answer", ["你好，请问需要办理什么业务？", "请补充毕业时间和就业情况。"])
def test_direct_answer_and_followup_are_not_lost(monkeypatch, answer):
    install_agent(monkeypatch, [AIMessage(content=answer)])
    events = list(generator.generate_stream("你好"))
    assert [item["data"]["text"] for item in events if item["event"] == "delta"] == [answer]


def test_reasoning_blocks_and_tool_call_text_are_not_answer_text():
    assert generator.extract_stream_text(tool_turn("I'll check.", "call-1")) == ""
    message = AIMessage(content=[
        {"type": "reasoning", "text": "internal reasoning"},
        {"type": "thinking", "content": "internal thinking"},
        {"type": "text", "text": "正式回答"},
    ])
    assert generator.extract_stream_text(message) == "正式回答"


def test_interrupted_model_does_not_publish_unclassified_preamble(monkeypatch):
    class InterruptedAgent:
        def stream(self, *args, **kwargs):
            yield "messages", (AIMessageChunk(content="I'll look into it."), {})
            raise RuntimeError("provider interrupted")

    monkeypatch.setattr(generator, "_make_agent", lambda *args: InterruptedAgent())
    events = []
    with pytest.raises(RuntimeError, match="provider interrupted"):
        for event in generator.generate_stream("有哪些政策？"):
            events.append(event)
    assert not any(event["event"] == "delta" for event in events)
