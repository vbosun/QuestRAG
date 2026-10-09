"""Standalone Browser Use worker.

Install this package in a separate virtual environment with
``browser-use[core]``. It intentionally has no dependency on QuestRAG.
"""
import asyncio
import json
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
    profile_name: str | None = Field(default=None, max_length=120)


class TaskRecord(BaseModel):
    task_id: str
    session_id: str
    status: str
    url: str
    task: str
    events: list[dict] = Field(default_factory=list)
    result: str | None = None
    error: str | None = None
    observed_page: dict | None = None


TASKS: dict[str, TaskRecord] = {}
RUNNERS: dict[str, asyncio.Task] = {}
MAX_CONCURRENT = max(1, int(os.environ.get("BROWSER_USE_MAX_CONCURRENT", "1")))
MAX_PENDING = max(MAX_CONCURRENT, int(os.environ.get("BROWSER_USE_MAX_PENDING", "4")))
TASK_TIMEOUT = max(10, int(os.environ.get("BROWSER_USE_TIMEOUT_SECONDS", "300")))
CAPACITY = asyncio.Semaphore(MAX_CONCURRENT)


@app.get("/health")
def health():
    return {"status": "ok", "engine": "browser-use", "max_concurrent": MAX_CONCURRENT,
            "active_or_queued": len(RUNNERS),
            "model_configured": bool(os.environ.get("BROWSER_USE_API_KEY") or os.environ.get("OPENAI_API_KEY"))}


@app.post("/tasks", status_code=202)
async def run_task(req: TaskRequest):
    parsed = urlparse(req.url)
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    if parsed.scheme not in {"http", "https"} or ("*" not in ALLOWED_ORIGINS and origin not in ALLOWED_ORIGINS):
        raise HTTPException(status_code=403, detail=f"网页来源未加入白名单：{origin}")
    if len(RUNNERS) >= MAX_PENDING:
        raise HTTPException(status_code=429, detail="浏览器任务队列已满，请稍后重试")
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
        RUNNERS.pop(task_id, None)
        record.status = "cancelled"
        record.events.append(_event("cancelled", "已停止 Browser Use 操作"))
    return _public(record)


async def _execute(task_id: str, req: TaskRequest) -> None:
    record = TASKS[task_id]
    try:
        async with CAPACITY:
            record.status = "running"
            record.events.append(_event("running", "Agent 正在打开业务页面并识别可操作控件"))
            async with asyncio.timeout(TASK_TIMEOUT):
                await _run_agent(record, req)
    except asyncio.CancelledError:
        record.status = "cancelled"
        record.events.append(_event("cancelled", "已停止 Browser Use 操作"))
        raise
    except TimeoutError:
        record.status = "failed"
        record.error = "浏览器任务执行超时，请核对页面后重试"
        record.events.append(_event("failed", record.error))
    except Exception as exc:
        record.status = "failed"
        record.error = f"Browser Use 执行失败：{exc}"
        record.events.append(_event("failed", record.error))
    finally:
        RUNNERS.pop(task_id, None)


async def _run_agent(record: TaskRecord, req: TaskRequest) -> None:
    from browser_use import Agent, Browser, ChatOpenAI
    options = {"headless": True, "window_size": {"width": 1280, "height": 900}}
    if executable := os.environ.get("BROWSER_USE_CHROME_PATH"):
        options.update(executable_path=executable, chromium_sandbox=False)
    browser = Browser(**options)
    try:
        force_structured = os.environ.get("BROWSER_USE_FORCE_STRUCTURED_OUTPUT", "true").lower() in {"1", "true", "yes"}
        base_url = os.environ.get("BROWSER_USE_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or None
        llm_type = ChatOpenAI
        if not force_structured and urlparse(base_url or "").hostname == "api.deepseek.com":
            from browser_use_worker.deepseek_llm import DeepSeekJSONChat
            llm_type = DeepSeekJSONChat
        llm = llm_type(
            model=os.environ.get("BROWSER_USE_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini",
            api_key=os.environ.get("BROWSER_USE_API_KEY") or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url,
            dont_force_structured_output=not force_structured,
            add_schema_to_system_prompt=not force_structured,
        )
        use_vision = os.environ.get("BROWSER_USE_USE_VISION", "true").lower() in {"1", "true", "yes"}
        agent = Agent(task=req.task, initial_actions=_initial_actions(req), browser=browser, llm=llm, use_vision=use_vision)
        history = await agent.run(max_steps=req.max_steps)
        record.result = history.final_result() if hasattr(history, "final_result") else str(history)
        if hasattr(history, "is_successful") and history.is_successful() is not True:
            record.status = "failed"
            record.error = "Agent 未确认完成任务，请核对页面或重新执行"
            record.events.append(_event("failed", record.error))
        else:
            page = await browser.get_current_page()
            if page:
                record.observed_page = json.loads(await page.evaluate("""() => {
                    const roots=[document], fields=[];
                    for(let i=0;i<roots.length;i++) {
                        for(const el of roots[i].querySelectorAll('*')) {
                            if(el.shadowRoot) roots.push(el.shadowRoot);
                            if(['INPUT','SELECT','TEXTAREA'].includes(el.tagName) && el.type !== 'file')
                                fields.push({key:el.name||el.id,value:el.value,valid:el.validity.valid});
                        }
                    }
                    return {url:location.href,title:document.title,fields};
                }"""))
            record.status = "completed"
            record.events.append(_event("completed", "Agent 已完成本次页面操作"))
    finally:
        close = getattr(browser, "kill", None) or getattr(browser, "close", None)
        if close:
            value = close()
            if hasattr(value, "__await__"):
                await value


def _initial_actions(req: TaskRequest) -> list[dict]:
    actions = [{"navigate": {"url": req.url, "new_tab": False}}]
    if req.profile_name and urlparse(req.url).path in {"/employment-registration/apply", "/unemployment-registration/apply"}:
        # Only the server-supplied identity is prefilled. The agent fills the
        # remaining editable fields. The mock bridge keeps identity read-only.
        fields = json.dumps({"full_name": req.profile_name})
        actions.append({"evaluate": {"code": f"window.postMessage({{type:'agent-form-state',fields:{fields}}},location.origin);"}})
    return actions


def _event(kind: str, message: str) -> dict:
    return {"kind": kind, "message": message, "at": datetime.now(timezone.utc).isoformat()}


def _public(record: TaskRecord) -> dict:
    return record.model_dump()
