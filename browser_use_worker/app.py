"""Standalone Browser Use worker.

Install this package in a separate virtual environment with
``browser-use[core]``. It intentionally has no dependency on QuestRAG.
"""
import os
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="QuestRAG Browser Use Worker", version="0.1.0")
ALLOWED_ORIGINS = tuple(item.strip().rstrip("/") for item in os.environ.get("BROWSER_ALLOWED_ORIGINS", "http://127.0.0.1:8020,http://localhost:8020").split(",") if item.strip())


class TaskRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=120)
    url: str
    task: str = Field(min_length=1, max_length=4000)
    max_steps: int = Field(default=30, ge=1, le=100)


@app.get("/health")
def health():
    return {"status": "ok", "engine": "browser-use"}


@app.post("/tasks")
async def run_task(req: TaskRequest):
    parsed = urlparse(req.url)
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    if parsed.scheme not in {"http", "https"} or ("*" not in ALLOWED_ORIGINS and origin not in ALLOWED_ORIGINS):
        raise HTTPException(status_code=403, detail=f"网页来源未加入白名单：{origin}")
    try:
        from browser_use import Agent, Browser, ChatOpenAI
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Browser Use worker 环境未安装 browser-use[core]") from exc
    browser = Browser(headless=True, window_size={"width": 1280, "height": 900})
    try:
        llm = ChatOpenAI(model=os.environ.get("BROWSER_USE_MODEL", "gpt-4.1-mini"))
        agent = Agent(task=f"打开 {req.url}。{req.task}", browser=browser, llm=llm)
        history = await agent.run(max_steps=req.max_steps)
        result = history.final_result() if hasattr(history, "final_result") else str(history)
        return {"session_id": req.session_id, "status": "completed", "result": result}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Browser Use 执行失败：{exc}") from exc
    finally:
        close = getattr(browser, "close", None)
        if close:
            value = close()
            if hasattr(value, "__await__"):
                await value
