"""Optional Browser Use adapter for generic, goal-driven browser tasks.

Browser Use owns the agent loop; QuestRAG owns authorization, session identity
and the task boundary. The import is lazy so Playwright/embedded modes do not
require Browser Use credentials or native packages.
"""
from urllib.parse import urlparse

from fastapi import HTTPException

from quest_rag.core.config import BROWSER_ALLOWED_ORIGINS, BROWSER_USE_WORKER_URL


class BrowserUseRuntime:
    def __init__(self):
        self._agents: dict[str, object] = {}

    async def run(self, session_id: str, url: str, task: str, max_steps: int = 30) -> dict:
        origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}".rstrip("/")
        if origin not in BROWSER_ALLOWED_ORIGINS and "*" not in BROWSER_ALLOWED_ORIGINS:
            raise HTTPException(status_code=403, detail=f"网页来源未加入白名单：{origin}")
        if BROWSER_USE_WORKER_URL:
            import httpx
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.post(f"{BROWSER_USE_WORKER_URL}/tasks", json={"session_id": session_id, "url": url, "task": task, "max_steps": max_steps})
            if response.status_code >= 400:
                raise HTTPException(status_code=502, detail="Browser Use worker 执行失败")
            return response.json()
        raise HTTPException(status_code=503, detail="Browser Use 已接入但 worker 未配置，请设置 BROWSER_USE_WORKER_URL；固定表单可改用 Playwright 模式")


runtime = BrowserUseRuntime()
