"""Optional Browser Use adapter for goal-driven browser tasks.

Browser Use owns the agent loop. QuestRAG owns authorization, the application
case boundary and the task lifecycle exposed to the chat UI.
"""
from urllib.parse import urlparse

from fastapi import HTTPException

from quest_rag.core.config import BROWSER_ALLOWED_ORIGINS, BROWSER_USE_WORKER_URL


class BrowserUseRuntime:
    def __init__(self):
        self._owners: dict[str, int] = {}
        self._tasks: dict[str, str] = {}

    def register_session(self, session_id: str, owner_id: int) -> None:
        """Register a case or generic browser session without opening Chromium.

        Browser Use starts its own browser, so reusing the Playwright runtime
        here would create a second, unrelated page merely to establish access.
        """
        if session_id in self._owners and not self.owns(session_id, owner_id):
            raise HTTPException(status_code=404, detail="浏览器会话不存在")
        self._owners[session_id] = owner_id

    def owns(self, session_id: str, owner_id: int) -> bool:
        return self._owners.get(session_id) == owner_id

    async def run(self, session_id: str, url: str, task: str, max_steps: int = 30, profile_name: str | None = None,
                  presentation: str = "live", command_id: str | None = None, initial_fields: dict | None = None,
                  requested_fields: dict | None = None, page_id: str | None = None, field_revisions: dict | None = None) -> dict:
        origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}".rstrip("/")
        if origin not in BROWSER_ALLOWED_ORIGINS and "*" not in BROWSER_ALLOWED_ORIGINS:
            raise HTTPException(status_code=403, detail=f"网页来源未加入白名单：{origin}")
        if BROWSER_USE_WORKER_URL:
            import httpx
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post(f"{BROWSER_USE_WORKER_URL}/tasks", json={"session_id": session_id, "url": url, "task": task, "max_steps": max_steps, "profile_name": profile_name, "presentation": presentation,
                        "command_id": command_id, "initial_fields": initial_fields or {}, "requested_fields": requested_fields or {},
                        "page_id": page_id, "field_revisions": field_revisions or {}})
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=503, detail=f"Browser Use worker 不可用：{exc}") from exc
            if response.status_code >= 400:
                raise HTTPException(status_code=response.status_code if response.status_code in {409, 429} else 502, detail=_worker_error(response, "Browser Use worker 启动失败"))
            payload = response.json()
            task_id = payload.get("task_id")
            if not task_id:
                raise HTTPException(status_code=502, detail="Browser Use worker 未返回任务标识")
            self._tasks[session_id] = task_id
            return payload
        raise HTTPException(status_code=503, detail="Browser Use 已接入但 worker 未配置，请设置 BROWSER_USE_WORKER_URL；固定表单可改用 Playwright 模式")

    async def status(self, session_id: str) -> dict:
        task_id = self._tasks.get(session_id)
        if not task_id:
            return {"session_id": session_id, "status": "idle", "events": []}
        payload = await self._worker_request("GET", f"/tasks/{task_id}")
        if payload.get('command_id') and session_id in self._owners:
            from quest_rag.applications.page_sessions import pages
            page = pages.get(session_id, self._owners[session_id])
            requested = payload.get('requested_fields') or {}
            same_page = bool(page and page['open'] and page['page_id'] == payload.get('page_id'))
            acknowledged = bool(same_page and page.get('task_id') == task_id)
            applied = [key for key, value in requested.items() if acknowledged and page['fields'].get(key) == value
                       and payload.get('form_fields', {}).get(key) == value]
            conflicts = page.get('conflicts', []) if acknowledged else []
            payload['page_sync'] = {'status': 'applied' if len(applied) == len(requested) else 'conflict' if conflicts else 'pending',
                                    'applied_fields': applied, 'conflicts': conflicts}
            if conflicts:
                payload['view_error'] = '已保留任务开始后手动修改的字段：' + '、'.join(conflicts)
        return payload

    async def cancel(self, session_id: str) -> dict:
        task_id = self._tasks.get(session_id)
        if not task_id:
            return {"session_id": session_id, "status": "idle", "cancelled": False}
        payload = await self._worker_request("DELETE", f"/tasks/{task_id}")
        return {**payload, "cancelled": True}

    def _task_path(self, session_id: str) -> str:
        task_id = self._tasks.get(session_id)
        if not task_id:
            raise HTTPException(status_code=404, detail="浏览器会话不存在")
        return f"/tasks/{task_id}"

    async def act(self, session_id: str, action: str, value=None) -> dict:
        return await self._worker_request("POST", self._task_path(session_id) + "/action",
                                          json={"action": action, "value": value})

    async def upload(self, session_id: str, filename: str, content_type: str, content: bytes) -> dict:
        return await self._worker_request("POST", self._task_path(session_id) + "/upload",
                                          files={"file": (filename, content, content_type)})

    async def _worker_request(self, method: str, path: str, **kwargs) -> dict:
        if not BROWSER_USE_WORKER_URL:
            raise HTTPException(status_code=503, detail="Browser Use worker 未配置，请设置 BROWSER_USE_WORKER_URL")
        import httpx
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.request(method, f"{BROWSER_USE_WORKER_URL}{path}", **kwargs)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail=f"Browser Use worker 不可用：{exc}") from exc
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code if 400 <= response.status_code < 500 else 502,
                                detail=_worker_error(response, "Browser Use worker 请求失败"))
        return response.json()


def _worker_error(response, fallback: str) -> str:
    try:
        detail = response.json().get("detail")
        if isinstance(detail, str) and detail:
            return detail
    except ValueError:
        pass
    return fallback


runtime = BrowserUseRuntime()
