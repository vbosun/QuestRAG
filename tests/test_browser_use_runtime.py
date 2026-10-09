import asyncio
from types import SimpleNamespace

import pytest

from fastapi import HTTPException

from quest_rag.applications.browser_use_runtime import BrowserUseRuntime


def test_browser_use_runtime_tracks_session_owner_and_idle_state():
    runtime = BrowserUseRuntime()
    runtime.register_session("case-1", 42)

    assert runtime.owns("case-1", 42)
    assert not runtime.owns("case-1", 43)
    assert asyncio.run(runtime.status("case-1")) == {
        "session_id": "case-1",
        "status": "idle",
        "events": [],
    }


def test_browser_use_rejects_page_outside_allowlist(monkeypatch):
    runtime = BrowserUseRuntime()
    monkeypatch.setattr("quest_rag.applications.browser_use_runtime.BROWSER_ALLOWED_ORIGINS", ("http://127.0.0.1:8020",))

    try:
        asyncio.run(runtime.run("case-1", "https://untrusted.example/apply", "填写资料"))
    except HTTPException as exc:
        assert exc.status_code == 403
        assert "白名单" in str(exc.detail)
    else:
        raise AssertionError("expected allowlist rejection")


def test_browser_use_session_owner_cannot_be_replaced():
    runtime = BrowserUseRuntime()
    runtime.register_session('case-1', 42)
    runtime.register_session('case-1', 42)
    with pytest.raises(HTTPException) as error:
        runtime.register_session('case-1', 43)
    assert error.value.status_code == 404
    assert runtime.owns('case-1', 42)


@pytest.mark.parametrize('provider', ['browser_use', 'playwright', 'unknown'])
def test_generic_browser_task_cannot_claim_foreign_or_unknown_session(monkeypatch, provider):
    from quest_rag.api import browser
    from quest_rag.applications.playwright_runtime import PlaywrightRuntime

    browser_use = BrowserUseRuntime()
    playwright = PlaywrightRuntime()
    if provider == 'browser_use':
        browser_use.register_session('foreign-session', 42)
    if provider == 'playwright':
        playwright._owners['foreign-session'] = 42
    monkeypatch.setattr(browser, 'runtime', playwright)
    monkeypatch.setattr(browser, 'browser_use_runtime', browser_use)
    with pytest.raises(HTTPException) as error:
        asyncio.run(browser.run_browser_use('foreign-session', browser.BrowserTaskRequest(
            url='http://127.0.0.1:8020', task='test'), SimpleNamespace(id=43)))
    assert error.value.status_code == 404
    assert not browser_use.owns('foreign-session', 43)


def test_existing_authorized_playwright_session_can_start_browser_use_task(monkeypatch):
    from quest_rag.api import browser
    from quest_rag.applications.playwright_runtime import PlaywrightRuntime

    browser_use = BrowserUseRuntime()
    playwright = PlaywrightRuntime()
    playwright._owners['owned-session'] = 42
    monkeypatch.setattr(browser, 'runtime', playwright)
    monkeypatch.setattr(browser, 'browser_use_runtime', browser_use)

    async def fake_run(session_id, url, task, max_steps):
        assert browser_use.owns(session_id, 42)
        return {'status': 'queued'}

    monkeypatch.setattr(browser_use, 'run', fake_run)
    result = asyncio.run(browser.run_browser_use('owned-session', browser.BrowserTaskRequest(
        url='http://127.0.0.1:8020', task='test'), SimpleNamespace(id=42)))
    assert result['status'] == 'queued'
