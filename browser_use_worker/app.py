"""Standalone Browser Use worker.

Install this package in a separate virtual environment with
``browser-use[core]``. It intentionally has no dependency on QuestRAG.
"""
import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import urlparse
from typing import Literal

from fastapi import FastAPI, HTTPException, File, UploadFile
from pydantic import BaseModel, Field

@asynccontextmanager
async def lifespan(app):
    async def sweep():
        while True:
            await asyncio.sleep(30)
            for task_id, live in list(BROWSERS.items()):
                if task_id not in RUNNERS and time.monotonic() - live.last_seen > SESSION_TTL:
                    await _close_browser(task_id)
    cleaner = asyncio.create_task(sweep())
    yield
    cleaner.cancel()
    await asyncio.gather(cleaner, return_exceptions=True)
    for runner in list(RUNNERS.values()):
        runner.cancel()
    await asyncio.gather(*RUNNERS.values(), return_exceptions=True)
    for task_id in list(BROWSERS):
        await _close_browser(task_id)


app = FastAPI(title="QuestRAG Browser Use Worker", version="0.2.0", lifespan=lifespan)
ALLOWED_ORIGINS = tuple(item.strip().rstrip("/") for item in os.environ.get("BROWSER_ALLOWED_ORIGINS", "http://127.0.0.1:8020,http://localhost:8020").split(",") if item.strip())


class TaskRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=120)
    url: str
    task: str = Field(min_length=1, max_length=4000)
    max_steps: int = Field(default=30, ge=1, le=100)
    profile_name: str | None = Field(default=None, max_length=120)
    presentation: Literal["live", "iframe"] = "live"
    command_id: str | None = None
    initial_fields: dict[str, str] = Field(default_factory=dict)
    requested_fields: dict[str, str] = Field(default_factory=dict)
    page_id: str | None = None
    field_revisions: dict[str, int] = Field(default_factory=dict)


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
    page_available: bool = False
    live_frame: dict | None = None
    control: str = "agent"
    view_error: str | None = None
    presentation: Literal["live", "iframe"] = "live"
    operation_events: list[dict] = Field(default_factory=list)
    form_fields: dict = Field(default_factory=dict)
    command_id: str | None = None
    requested_fields: dict = Field(default_factory=dict)
    page_id: str | None = None
    field_revisions: dict = Field(default_factory=dict)


TASKS: dict[str, TaskRecord] = {}
RUNNERS: dict[str, asyncio.Task] = {}
BROWSERS: dict = {}
SESSION_TTL = max(60, int(os.environ.get("BROWSER_SESSION_TTL_SECONDS", "900")))
MAX_RETAINED = 2
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
    for record in reversed(list(TASKS.values())):
        if record.session_id == req.session_id and req.command_id:
            if record.command_id == req.command_id:
                return _public(record)
            if record.task_id in RUNNERS:
                raise HTTPException(409, detail="当前申请正在填写，请等待完成或停止后再修改")
            continue
        if record.session_id == req.session_id and (record.presentation == "iframe" or record.task_id in BROWSERS or record.task_id in RUNNERS):
            # Reopening must preserve manual edits and never launch a competing agent.
            return _public(record)
    if len(RUNNERS) >= MAX_PENDING:
        raise HTTPException(status_code=429, detail="浏览器任务队列已满，请稍后重试")
    task_id = str(uuid4())
    record = TaskRecord(task_id=task_id, session_id=req.session_id, status="queued", url=req.url, task=req.task,
                        presentation=req.presentation, command_id=req.command_id, requested_fields=req.requested_fields,
                        page_id=req.page_id, field_revisions=req.field_revisions)
    record.events.append(_event("queued", "已进入 Browser Use 执行队列"))
    TASKS[task_id] = record
    RUNNERS[task_id] = asyncio.create_task(_execute(task_id, req))
    return _public(record)


@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    record = TASKS.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Browser Use 任务不存在")
    if record.presentation == "live" and (live := BROWSERS.get(task_id)):
        try:
            record.live_frame = await live.capture(record.control == "agent")
            record.view_error = None
        except Exception:
            record.view_error = "画面暂时未更新，正在重新连接"
    return _public(record)


@app.delete("/tasks/{task_id}")
async def cancel_task(task_id: str):
    record = TASKS.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Browser Use 任务不存在")
    runner = RUNNERS.get(task_id)
    if record.status in {"queued", "running"} and runner:
        runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)
        record.status = "cancelled"
    record.control = "user"
    if record.presentation == "live" and task_id in BROWSERS:
        record.live_frame = await BROWSERS[task_id].capture(False)
    return _public(record)


class LiveAction(BaseModel):
    action: str
    value: object | None = None


def _manual_browser(task_id):
    record = TASKS.get(task_id)
    if not record or task_id not in BROWSERS:
        raise HTTPException(status_code=410, detail="浏览器会话已结束，请重新打开申请")
    if task_id in RUNNERS or record.control != "user":
        raise HTTPException(status_code=409, detail="请先接管页面，等待 Agent 停止后再操作")
    return BROWSERS[task_id]


@app.post("/tasks/{task_id}/action")
async def live_action(task_id: str, req: LiveAction):
    live = _manual_browser(task_id)
    await live.act(req.action, req.value)
    return await get_task(task_id)


@app.post("/tasks/{task_id}/upload")
async def live_upload(task_id: str, file: UploadFile = File(...)):
    live = _manual_browser(task_id)
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="材料不能超过 10 MB")
    await live.upload(file.filename or "材料", file.content_type or "application/octet-stream", content)
    return await get_task(task_id)


async def _close_browser(task_id):
    live = BROWSERS.pop(task_id, None)
    if live:
        await live.close()
    if record := TASKS.get(task_id):
        record.page_available = False
        record.live_frame = None


async def _execute(task_id: str, req: TaskRequest) -> None:
    record = TASKS[task_id]
    try:
        async with CAPACITY:
            while len(BROWSERS) >= MAX_RETAINED:
                old = next((key for key in BROWSERS if key not in RUNNERS), None)
                if old is None:
                    raise RuntimeError("浏览器会话已满")
                await _close_browser(old)
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
        record.control = "user"
        if record.presentation == "iframe":
            try:
                await _close_browser(task_id)
            except Exception:
                record.view_error = "后台浏览器资源释放失败"
        elif live := BROWSERS.get(task_id):
            try:
                record.live_frame = await live.capture(False)
            except Exception:
                pass
        RUNNERS.pop(task_id, None)


async def _run_agent(record: TaskRecord, req: TaskRequest) -> None:
    from browser_use import Agent, Browser, ChatOpenAI, Tools
    options = {"headless": True, "keep_alive": True, "window_size": {"width": 1280, "height": 900},
               "wait_between_actions": .8}
    if executable := os.environ.get("BROWSER_USE_CHROME_PATH"):
        options.update(executable_path=executable, chromium_sandbox=False)
    browser = Browser(**options)
    from browser_use_worker.live_browser import LiveBrowser
    live = LiveBrowser(browser)
    try:
        await browser.start()
        await live.connect()
        BROWSERS[record.task_id] = live
        record.page_available = True
        from browser_use_worker.operation_feedback import OperationFeedback
        feedback = OperationFeedback(record, live)
        for context in live.connection.contexts:
            await context.expose_binding("__questAgentTarget", feedback.target)

        class ObservedTools(Tools):
            async def act(self, action, *args, **kwargs):
                if req.command_id:
                    from browser_use.agent.views import ActionResult
                    actions = action.model_dump(exclude_unset=True)
                    name, params = next(iter(actions.items()))
                    if name not in {'navigate', 'input', 'select_dropdown', 'get_dropdown_options', 'done', 'wait', 'scroll', 'extract', 'find_elements'}:
                        return ActionResult(error='本次仅允许指定字段的 input/select_dropdown 和只读观察，禁止其他操作')
                    if name == 'navigate' and (params.get('url') != req.url or seeded):
                        return ActionResult(error='本次只能初始化当前申请页面，填写后不得跳转或重载')
                    if name in {'input', 'select_dropdown'}:
                        node = await browser.get_element_by_index(params['index'])
                        attrs = node.attributes if node else {}
                        key = attrs.get('name') or attrs.get('id')
                        if key not in req.requested_fields or 'readonly' in attrs or 'disabled' in attrs:
                            return ActionResult(error='该字段不属于本次明确要求填写的字段')
                event_start = len(record.operation_events)
                async def invoke():
                    return await super(ObservedTools, self).act(action, *args, **kwargs)
                result = await feedback.perform(action.model_dump(exclude_unset=True), invoke)
                confirmed = {event['field_key']: event['value']
                             for event in record.operation_events[event_start:] if event['phase'] == 'applied'}
                if confirmed and not result.error:
                    readback = "页面实际回读确认：" + json.dumps(confirmed, ensure_ascii=False)
                    result.extracted_content = (result.extracted_content or "") + "\n" + readback
                    result.long_term_memory = (result.long_term_memory or "") + "\n" + readback
                return result
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
        planning_options = {"max_actions_per_step": 1}
        if record.presentation == "iframe":
            planning_options.update(
                max_actions_per_step=12,
                extend_system_message=(
                    "填写申请表时，先统一规划当前页面已确认信息对应的可编辑字段，在同一轮 action 列表中"
                    "按页面顺序给出多个字段的操作，最多 12 个动作；不要每填一个字段就结束本轮。"
                    "每个 action 只操作一个字段，优先使用 input 和 select_dropdown，逐项执行并校验。"
                    "evaluate 会中断当前动作队列，仅在普通输入无法操作时单独使用，"
                    "不要用一个 evaluate 脚本同时修改多个字段。"
                    "工具返回的‘页面实际回读确认’是执行后读取的真实字段值，可用于完成核对；"
                    "全部已知字段回读值正确时直接单独调用 done，不必再用脚本重复核对。"
                    "未知信息保持空白，只读字段保持原值，禁止提交、确认或下一步。"
                    "依赖前一个选择后才出现的字段需先观察实际变化，再规划剩余字段；"
                    "失败后先核对当前页面和已成功字段，再修正剩余动作。done 必须在填写完成后单独调用。"
                ),
            )
        agent = Agent(task=req.task, initial_actions=_initial_actions(req), browser=browser, llm=llm,
                      tools=ObservedTools() if record.presentation == "iframe" else None,
                      use_vision=use_vision, **planning_options)
        seeded = False
        async def seed_identity(_agent):
            nonlocal seeded
            if not seeded and (req.profile_name or req.initial_fields) and urlparse(req.url).path in {"/employment-registration/apply", "/unemployment-registration/apply"}:
                # Navigation terminates Browser Use's initial action batch.
                page = await live.page()
                fields = {**req.initial_fields}
                if req.profile_name:
                    fields['full_name'] = req.profile_name
                async def seed():
                    await page.evaluate("fields => window.postMessage({type:'agent-form-state',fields,allow_empty:true}, location.origin)", fields)
                    await page.wait_for_function("fields => Object.entries(fields).every(([key,value]) => document.querySelector('#applicationForm')?.elements.namedItem(key)?.value === value)",
                                                 arg=fields, timeout=3000)
                if req.command_id:
                    await seed()  # baseline restoration is not an AI filling event
                else:
                    await feedback.perform({"seed_identity": {}}, seed)
                seeded = True
                record.events.append(_event("identity_ready", "姓名已按档案带入，正在填写其他信息"))
        history = await agent.run(max_steps=req.max_steps, on_step_start=seed_identity)
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
        if record.task_id not in BROWSERS:
            await live.close()


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
