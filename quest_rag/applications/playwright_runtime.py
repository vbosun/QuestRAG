"""Per-case Playwright runtime for the Agent execution mode."""
import base64
from typing import Any
from fastapi import HTTPException


class PlaywrightRuntime:
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._contexts: dict[str, Any] = {}
        self._pages: dict[str, Any] = {}

    async def _ensure_browser(self):
        if self._browser:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise HTTPException(status_code=503, detail="Playwright 未安装，请安装浏览器执行依赖") from exc
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)

    async def start(self, case_id: str, url: str, fields: dict[str, Any] | None = None) -> dict:
        await self._ensure_browser()
        context = self._contexts.get(case_id) or await self._browser.new_context(viewport={"width": 1280, "height": 900})
        self._contexts[case_id] = context
        page = self._pages.get(case_id) or await context.new_page()
        self._pages[case_id] = page
        if page.url != url:
            await page.goto(url, wait_until="domcontentloaded")
        for key, value in (fields or {}).items():
            await self._fill(page, key, value)
        return await self.observe(case_id)

    async def observe(self, case_id: str) -> dict:
        page = self._pages.get(case_id)
        if not page:
            raise HTTPException(status_code=404, detail="Playwright 浏览器会话不存在")
        fields = await page.locator("input, select, textarea").evaluate_all("""els => els.map(el => ({key: el.name || el.id || el.type, label: el.labels?.[0]?.innerText || el.getAttribute('aria-label') || el.name || el.id, type: el.tagName.toLowerCase() === 'select' ? 'select' : (el.type || el.tagName.toLowerCase()), value: el.value, options: el.tagName.toLowerCase() === 'select' ? Array.from(el.options).map(o => ({label:o.textContent.trim(), value:o.value})) : undefined}))""")
        image = await page.screenshot(type="png")
        return {"url": page.url, "title": await page.title(), "fields": fields, "screenshot": base64.b64encode(image).decode("ascii")}

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
        else:
            raise HTTPException(status_code=422, detail="不支持的浏览器操作")
        return await self.observe(case_id)

    async def _fill(self, page, key: str, value: Any):
        locator = page.get_by_label(key, exact=True)
        if await locator.count() == 0:
            locator = page.locator(f"[name='{key}'], #{key}").first
        if await locator.count():
            await locator.fill(str(value)[:10] if await locator.get_attribute("type") == "date" else str(value))


runtime = PlaywrightRuntime()
