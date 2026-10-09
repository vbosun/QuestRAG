import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from browser_use_worker import app as worker


def test_manual_input_is_blocked_until_agent_releases_control(monkeypatch):
    record = worker.TaskRecord(task_id="t", session_id="s", status="running", url="http://demo", task="test")
    live = object()
    monkeypatch.setattr(worker, "TASKS", {"t": record})
    monkeypatch.setattr(worker, "BROWSERS", {"t": live})
    monkeypatch.setattr(worker, "RUNNERS", {"t": object()})
    with pytest.raises(HTTPException) as error:
        worker._manual_browser("t")
    assert error.value.status_code == 409
    record.control = "user"
    # Status alone cannot release control while an action is still in flight.
    with pytest.raises(HTTPException):
        worker._manual_browser("t")
    worker.RUNNERS.clear()
    assert worker._manual_browser("t") is live


def test_reopening_same_case_reuses_page_and_manual_edits(monkeypatch):
    record = worker.TaskRecord(task_id="t", session_id="s", status="completed", control="user",
                               url="http://demo/apply", task="test", page_available=True)
    monkeypatch.setattr(worker, "TASKS", {"t": record})
    monkeypatch.setattr(worker, "BROWSERS", {"t": object()})
    monkeypatch.setattr(worker, "RUNNERS", {})
    monkeypatch.setattr(worker, "ALLOWED_ORIGINS", ("http://demo",))
    result = asyncio.run(worker.run_task(worker.TaskRequest(session_id="s", url=record.url, task="test")))
    assert result["task_id"] == "t"
    assert result["control"] == "user"
    assert not worker.RUNNERS


def test_takeover_waits_for_agent_cleanup_and_preserves_browser(monkeypatch):
    async def scenario():
        record = worker.TaskRecord(task_id="t", session_id="s", status="running", url="http://demo", task="test")
        finished = []
        async def running():
            try:
                await asyncio.sleep(100)
            finally:
                await asyncio.sleep(.01)
                finished.append(True)
                worker.RUNNERS.pop("t", None)
        async def capture(enabled):
            assert finished and not enabled
            return {"image": "same-browser"}
        live = SimpleNamespace(capture=capture)
        monkeypatch.setattr(worker, "TASKS", {"t": record})
        monkeypatch.setattr(worker, "BROWSERS", {"t": live})
        monkeypatch.setattr(worker, "RUNNERS", {"t": asyncio.create_task(running())})
        await asyncio.sleep(0)
        result = await worker.cancel_task("t")
        assert result["control"] == "user"
        assert worker.BROWSERS["t"] is live
    asyncio.run(scenario())


def test_browser_actions_require_case_ownership(monkeypatch):
    from quest_rag.api import applications
    called = []
    def reject(user, case_id):
        raise HTTPException(status_code=404, detail="不存在")
    async def act(*args):
        called.append(args)
    monkeypatch.setattr(applications.service, "_require_case", reject)
    monkeypatch.setattr(applications.browser_use_runtime, "act", act)
    with pytest.raises(HTTPException) as error:
        asyncio.run(applications.act_application_browser_use(
            applications.BrowserActionRequest(case_id="foreign", action="type", target="", value="secret"),
            SimpleNamespace(id=123)))
    assert error.value.status_code == 404
    assert not called


def test_agent_task_excludes_readonly_identity_and_passes_it_only_to_seed(monkeypatch):
    from quest_rag.api import applications
    detail = {"execution_mode": "browser_use", "fields": [
        {"key": "full_name", "label": "姓名", "value": "测试用户", "editable": False},
        {"key": "phone", "label": "电话", "value": "13700000000", "editable": True},
    ]}
    monkeypatch.setattr(applications.service, "get_application_detail", lambda *args: detail)
    monkeypatch.setattr(applications.service, "connect_browser", lambda *args: {"entry_url": "http://demo/apply"})
    monkeypatch.setattr(applications.browser_use_runtime, "register_session", lambda *args: None)
    async def run(session_id, url, task, profile_name):
        assert "姓名=" not in task
        assert "电话=13700000000" in task
        assert "禁止清空" in task
        assert profile_name == "测试用户"
        return {"status": "queued"}
    monkeypatch.setattr(applications.browser_use_runtime, "run", run)
    assert asyncio.run(applications.start_application_browser_use(
        applications.BrowserConnectRequest(case_id="s"), SimpleNamespace(id=1)))["status"] == "queued"


def test_live_view_matches_agent_target_even_with_duplicate_tab_urls():
    from browser_use_worker.live_browser import LiveBrowser
    class Page:
        def __init__(self, target):
            self.target = target
            self.url = "http://demo/same-url"
        def is_closed(self):
            return False
    class CDP:
        def __init__(self, page):
            self.page = page
        async def send(self, method):
            return {"targetInfo": {"targetId": self.page.target}}
        async def detach(self):
            pass
    async def target():
        return {"targetId": "agent-tab"}
    async def session(page):
        return CDP(page)
    agent_page, other = Page("agent-tab"), Page("other-tab")
    live = LiveBrowser(SimpleNamespace(get_current_target_info=target))
    live.connection = SimpleNamespace(contexts=[SimpleNamespace(pages=[agent_page, other], new_cdp_session=session)])
    assert asyncio.run(live.page()) is agent_page
