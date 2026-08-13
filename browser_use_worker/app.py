"""Standalone Browser Use worker.

Install this package in a separate virtual environment with
``browser-use[core]``. It intentionally has no dependency on QuestRAG.
"""
import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4
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


class TaskRecord(BaseModel):
    task_id: str
    session_id: str
    status: str
    url: str
    task: str
    events: list[dict] = Field(default_factory=list)
    result: str | None = None
    error: str | None = None


TASKS: dict[str, TaskRecord] = {}
RUNNERS: dict[str, asyncio.Task] = {}


@app.get("/health")
def health():
    return {"status": "ok", "engine": "browser-use"}


@app.post("/tasks", status_code=202)
async def run_task(req: TaskRequest):
    parsed = urlparse(req.url)
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    if parsed.scheme not in {"http", "https"} or ("*" not in ALLOWED_ORIGINS and origin not in ALLOWED_ORIGINS):
        raise HTTPException(status_code=403, detail=f"网页来源未加入白名单：{origin}")
    task_id = str(uuid4())
    record = TaskRecord(task_id=task_id, session_id=req.session_id, status="queued", url=req.url, task=req.task)
    record.events.append(_event("queued", "已进入 Browser Use 执行队列"))
    TASKS[task_id] = record
    RUNNERS[task_id] = asyncio.create_task(_execute(task_id, req))
    return _public(record)


@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    record = TASKS.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Browser Use 任务不存在")
    return _public(record)


@app.delete("/tasks/{task_id}")
async def cancel_task(task_id: str):
    record = TASKS.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Browser Use 任务不存在")
    runner = RUNNERS.get(task_id)
    if record.status in {"queued", "running"} and runner:
        runner.cancel()
        record.status = "cancelled"
        record.events.append(_event("cancelled", "已停止 Browser Use 操作"))
    return _public(record)


async def _execute(task_id: str, req: TaskRequest) -> None:
    record = TASKS[task_id]
    record.status = "running"
    record.events.append(_event("running", "Agent 正在打开业务页面并识别可操作控件"))
    browser = None
    try:
        from browser_use import Agent, Browser, ChatOpenAI
        browser = Browser(headless=True, window_size={"width": 1280, "height": 900})
        llm = ChatOpenAI(model=os.environ.get("BROWSER_USE_MODEL", "gpt-4.1-mini"))
        agent = Agent(task=f"打开 {req.url}。{req.task}", browser=browser, llm=llm)
        history = await agent.run(max_steps=req.max_steps)
        result = history.final_result() if hasattr(history, "final_result") else str(history)
        record.status = "completed"
        record.result = result
        record.events.append(_event("completed", "Agent 已完成本次页面操作"))
    except asyncio.CancelledError:
        record.status = "cancelled"
        record.events.append(_event("cancelled", "已停止 Browser Use 操作"))
        raise
    except Exception as exc:
        record.status = "failed"
        record.error = f"Browser Use 执行失败：{exc}"
        record.events.append(_event("failed", record.error))
    finally:
        RUNNERS.pop(task_id, None)
        if browser:
            close = getattr(browser, "close", None)
            if close:
                value = close()
                if hasattr(value, "__await__"):
                    await value


def _event(kind: str, message: str) -> dict:
    return {"kind": kind, "message": message, "at": datetime.now(timezone.utc).isoformat()}


def _public(record: TaskRecord) -> dict:
    return record.model_dump()
