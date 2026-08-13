import asyncio

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
