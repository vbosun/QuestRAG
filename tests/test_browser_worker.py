import asyncio

import pytest
from fastapi import HTTPException
from browser_use_worker import app as worker


def test_worker_runs_one_browser_at_a_time_and_queued_task_can_be_cancelled(monkeypatch):
    async def scenario():
        monkeypatch.setattr(worker, "CAPACITY", asyncio.Semaphore(1))
        monkeypatch.setattr(worker, "TASKS", {})
        monkeypatch.setattr(worker, "RUNNERS", {})
        monkeypatch.setattr(worker, "ALLOWED_ORIGINS", ("http://mock-business:8020",))
        entered = asyncio.Event()
        release = asyncio.Event()
        running = []

        async def fake_agent(record, req):
            running.append(record.task_id)
            entered.set()
            await release.wait()
            record.status = "completed"

        monkeypatch.setattr(worker, "_run_agent", fake_agent)
        req = worker.TaskRequest(session_id="demo", url="http://mock-business:8020/apply", task="test")
        first = await worker.run_task(req)
        await entered.wait()
        second = await worker.run_task(req)
        await asyncio.sleep(0)
        assert worker.TASKS[second["task_id"]].status == "queued"
        assert len(running) == 1
        await worker.cancel_task(second["task_id"])
        release.set()
        await asyncio.gather(*worker.RUNNERS.values(), return_exceptions=True)
        assert worker.TASKS[first["task_id"]].status == "completed"
        assert worker.TASKS[second["task_id"]].status == "cancelled"
        assert not worker.RUNNERS

    asyncio.run(scenario())


def test_worker_rejects_tasks_when_queue_is_full(monkeypatch):
    monkeypatch.setattr(worker, "MAX_PENDING", 1)
    monkeypatch.setattr(worker, "RUNNERS", {"busy": object()})
    monkeypatch.setattr(worker, "ALLOWED_ORIGINS", ("http://mock-business:8020",))
    with pytest.raises(HTTPException) as error:
        asyncio.run(worker.run_task(worker.TaskRequest(
            session_id="demo", url="http://mock-business:8020/apply", task="test")))
    assert error.value.status_code == 429


def test_initial_navigation_keeps_task_text_out_of_url_and_prefills_only_identity():
    req = worker.TaskRequest(session_id="demo", url="http://mock-business:8020/employment-registration/apply?case_id=case-1", task="填写表单。不要提交", profile_name='测试"用户')
    actions = worker._initial_actions(req)
    assert actions[0]["navigate"]["url"] == req.url
    assert req.task not in str(actions)
    assert 'agent-form-state' in actions[1]["evaluate"]["code"]
    assert 'full_name' in actions[1]["evaluate"]["code"]
    assert 'phone' not in actions[1]["evaluate"]["code"]
    assert len(worker._initial_actions(req.model_copy(update={"url": "http://mock-business:8020/another-page"}))) == 1
