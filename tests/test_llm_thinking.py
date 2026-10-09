import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel

from quest_rag.rag import llm as llm_module


@pytest.mark.parametrize("model", [None, "deepseek-v4-flash", "deepseek-v4-pro", "gpt-4.1-mini"])
@pytest.mark.parametrize("stream", [False, True])
def test_chat_request_disables_deepseek_thinking(monkeypatch, model, stream):
    requests = []

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if payload.get("stream"):
            chunk = {"id": "test", "object": "chat.completion.chunk", "created": 0,
                     "model": payload["model"], "choices": [
                         {"index": 0, "delta": {"role": "assistant", "content": "你好"},
                          "finish_reason": None}]}
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  text=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n")
        return httpx.Response(200, json={"id": "test", "object": "chat.completion", "created": 0,
                                        "model": payload["model"], "choices": [
                                            {"index": 0, "message": {"role": "assistant", "content": "你好"},
                                             "finish_reason": "stop"}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(llm_module, "httpx", SimpleNamespace(Client=lambda **kwargs: client))
        monkeypatch.setattr(llm_module, "OPENAI_API_KEY", "test-key")
        monkeypatch.setattr(llm_module, "OPENAI_BASE_URL", "https://model.test/v1")
        monkeypatch.setattr(llm_module, "OPENAI_MODEL", "deepseek-v4-flash")
        llm = llm_module.make_llm(model=model, temperature=0.3, top_p=0.9)
        answer = "".join(chunk.content for chunk in llm.stream("你好")) if stream else llm.invoke("你好").content

    assert answer == "你好"
    assert len(requests) == 1
    payload = requests[0]
    if model is None or model.startswith("deepseek"):
        assert payload["thinking"] == {"type": "disabled"}
    else:
        assert "thinking" not in payload
    assert "extra_body" not in payload
    assert payload["temperature"] == 0.3
    assert payload["top_p"] == 0.9


@pytest.mark.parametrize("model", [None, "deepseek-v4-pro", "gpt-4.1-mini"])
def test_ragas_judge_request_disables_deepseek_thinking(monkeypatch, model):
    import ragas.llms
    from openai import AsyncOpenAI
    from quest_rag import evaluation_ragas

    requests = []
    judges = []
    real_factory = ragas.llms.llm_factory

    class JudgeResponse(BaseModel):
        ok: bool

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        message = {"role": "assistant", "content": '{"ok": true}'}
        if payload.get("tools"):
            message["tool_calls"] = [{"id": "call-test", "type": "function", "function": {
                "name": payload["tools"][0]["function"]["name"], "arguments": '{"ok": true}'}}]
        return httpx.Response(200, json={"id": "test", "object": "chat.completion", "created": 0,
                                        "model": payload["model"], "choices": [
                                            {"index": 0, "message": message, "finish_reason": "stop"}]})

    def capture_factory(*args, **kwargs):
        judge = real_factory(*args, **kwargs)
        judges.append(judge)
        return judge

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            monkeypatch.setattr(evaluation_ragas, "AsyncOpenAI", lambda **kwargs: AsyncOpenAI(
                api_key="test-key", base_url="https://model.test/v1", http_client=client))
            await evaluation_ragas._score_with_collections(
                question="test", answer="test", contexts=["test"], reference="test", metrics=[], model=model)
            response = await judges[0].agenerate("Return ok=true", JudgeResponse)
            assert response.ok

    monkeypatch.setattr(ragas.llms, "llm_factory", capture_factory)
    monkeypatch.setattr(evaluation_ragas, "OPENAI_MODEL", "deepseek-v4-flash")
    monkeypatch.setattr(evaluation_ragas, "_write_ragas_log", lambda payload: None)
    asyncio.run(run())
    assert len(requests) == 1
    if model is None or model.startswith("deepseek"):
        assert requests[0]["thinking"] == {"type": "disabled"}
    else:
        assert "thinking" not in requests[0]
