"""Per-case Playwright runtime for the Agent execution mode."""
import base64
import uuid
from urllib.parse import urlparse
from typing import Any
from fastapi import HTTPException
from quest_rag.core.config import BROWSER_ALLOWED_ORIGINS


class PlaywrightRuntime:
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._contexts: dict[str, Any] = {}
        self._pages: dict[str, Any] = {}
        self._owners: dict[str, int] = {}
        self._urls: dict[str, str] = {}

    async def _ensure_browser(self):
        if self._browser:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise HTTPException(status_code=503, detail="Playwright 未安装，请安装浏览器执行依赖") from exc
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)

    async def start(self, case_id: str, url: str, fields: dict[str, Any] | None = None, owner_id: int | None = None) -> dict:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=422, detail="只允许打开 http/https 网页")
        if "*" not in BROWSER_ALLOWED_ORIGINS and origin not in BROWSER_ALLOWED_ORIGINS:
            raise HTTPException(status_code=403, detail=f"网页来源未加入白名单：{origin}")
        await self._ensure_browser()
        context = self._contexts.get(case_id) or await self._browser.new_context(viewport={"width": 1280, "height": 900})
        self._contexts[case_id] = context
        if owner_id is not None:
            self._owners[case_id] = owner_id
        page = self._pages.get(case_id) or await context.new_page()
        self._pages[case_id] = page
        if page.url != url:
            await page.goto(url, wait_until="domcontentloaded")
        if fields and parsed.path in {"/employment-registration/apply", "/unemployment-registration/apply"}:
            # The demo bridge can populate the read-only identity field from
            # already authorized values without placing personal data in URLs.
            await page.evaluate("fields => window.postMessage({type:'agent-form-state',fields}, location.origin)", fields)
            if fields.get("full_name"):
                await page.wait_for_function("name => document.querySelector('#full_name')?.value === name", arg=str(fields["full_name"]), timeout=3000)
        prefill_results = []
        for key, value in (fields or {}).items():
            prefill_results.append(await self._fill(page, key, value))
        observed = await self.observe(case_id)
        observed["prefill"] = prefill_results
        return observed

    async def create_session(self, owner_id: int, url: str) -> dict:
        session_id = str(uuid.uuid4())
        self._owners[session_id] = owner_id
        self._urls[session_id] = url
        observed = await self.start(session_id, url)
        return {"session_id": session_id, "mode": "playwright", "page": observed}

    def owns(self, session_id: str, owner_id: int) -> bool:
        return self._owners.get(session_id) == owner_id

    async def close_session(self, session_id: str):
        page = self._pages.pop(session_id, None)
        context = self._contexts.pop(session_id, None)
        self._owners.pop(session_id, None)
        self._urls.pop(session_id, None)
        if page:
            await page.close()
        if context:
            await context.close()

    async def observe(self, case_id: str) -> dict:
        page = self._pages.get(case_id)
        if not page:
            raise HTTPException(status_code=404, detail="Playwright 浏览器会话不存在")
        fields = await page.locator("input, select, textarea").evaluate_all("""els => els.map(el => ({key: el.name || el.id || el.type, label: el.labels?.[0]?.innerText || el.getAttribute('aria-label') || el.name || el.id, type: el.tagName.toLowerCase() === 'select' ? 'select' : (el.type || el.tagName.toLowerCase()), value: el.value, options: el.tagName.toLowerCase() === 'select' ? Array.from(el.options).map(o => ({label:o.textContent.trim(), value:o.value})) : undefined}))""")
        controls = await page.locator("button, a, [role='button'], [role='link']").evaluate_all("""els => els.map(el => ({role: el.getAttribute('role') || el.tagName.toLowerCase(), label: (el.innerText || el.getAttribute('aria-label') || '').trim(), disabled: el.disabled || el.getAttribute('aria-disabled') === 'true'})).filter(el => el.label)""")
        frames = [{"url": frame.url, "name": frame.name} for frame in page.frames]
        image = await page.screenshot(type="png")
        return {"url": page.url, "title": await page.title(), "fields": fields, "controls": controls, "frames": frames, "screenshot": base64.b64encode(image).decode("ascii")}

    async def act(self, case_id: str, action: str, target: str, value: Any = None) -> dict:
        page = self._pages.get(case_id)
        if not page:
            raise HTTPException(status_code=404, detail="Playwright 浏览器会话不存在")
        if action == "fill":
            await self._fill(page, target, value)
        elif action == "select":
            await page.get_by_label(target, exact=True).select_option(label=str(value))
        elif action == "check":
            await page.get_by_label(target, exact=True).check()
        elif action == "click":
            await page.get_by_role("button", name=target, exact=True).click()
        elif action == "click_point":
            point = value or {}
            await page.mouse.click(float(point.get("x", 0)), float(point.get("y", 0)))
        elif action == "type":
            await page.keyboard.insert_text(str(value or ""))
        elif action == "key":
            await page.keyboard.press(str(value or ""))
        elif action == "wheel":
            point = value or {}
            await page.mouse.wheel(float(point.get("delta_x", 0)), float(point.get("delta_y", 0)))
        else:
            raise HTTPException(status_code=422, detail="不支持的浏览器操作")
        return await self.observe(case_id)

    async def _fill(self, page, key: str, value: Any):
        locator = page.get_by_label(key, exact=True)
        if await locator.count() == 0:
            locator = page.locator(f"[name='{key}'], #{key}").first
        if await locator.count():
            if await locator.get_attribute("readonly") is not None or await locator.get_attribute("disabled") is not None:
                return {"key": key, "status": "skipped", "reason": "readonly_or_disabled"}
            if (await locator.get_attribute("type") or "").lower() == "select" or await locator.evaluate("el => el.tagName.toLowerCase() === 'select'"):
                try:
                    await locator.select_option(value=str(value))
                except Exception:
                    await locator.select_option(label=str(value))
                return {"key": key, "status": "selected"}
            await locator.fill(str(value)[:10] if await locator.get_attribute("type") == "date" else str(value))
            return {"key": key, "status": "filled"}
        return {"key": key, "status": "not_found"}


runtime = PlaywrightRuntime()
