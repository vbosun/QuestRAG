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
        self._owners[session_id] = owner_id

    def owns(self, session_id: str, owner_id: int) -> bool:
        return self._owners.get(session_id) == owner_id

    async def run(self, session_id: str, url: str, task: str, max_steps: int = 30) -> dict:
        origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}".rstrip("/")
        if origin not in BROWSER_ALLOWED_ORIGINS and "*" not in BROWSER_ALLOWED_ORIGINS:
            raise HTTPException(status_code=403, detail=f"网页来源未加入白名单：{origin}")
        if BROWSER_USE_WORKER_URL:
            import httpx
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post(f"{BROWSER_USE_WORKER_URL}/tasks", json={"session_id": session_id, "url": url, "task": task, "max_steps": max_steps})
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=503, detail=f"Browser Use worker 不可用：{exc}") from exc
            if response.status_code >= 400:
                raise HTTPException(status_code=502, detail=_worker_error(response, "Browser Use worker 启动失败"))
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
        return await self._worker_request("GET", f"/tasks/{task_id}")

    async def cancel(self, session_id: str) -> dict:
        task_id = self._tasks.get(session_id)
        if not task_id:
            return {"session_id": session_id, "status": "idle", "cancelled": False}
        payload = await self._worker_request("DELETE", f"/tasks/{task_id}")
        return {**payload, "cancelled": True}

    async def _worker_request(self, method: str, path: str) -> dict:
        if not BROWSER_USE_WORKER_URL:
            raise HTTPException(status_code=503, detail="Browser Use worker 未配置，请设置 BROWSER_USE_WORKER_URL")
        import httpx
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.request(method, f"{BROWSER_USE_WORKER_URL}{path}")
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail=f"Browser Use worker 不可用：{exc}") from exc
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=_worker_error(response, "Browser Use worker 请求失败"))
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
