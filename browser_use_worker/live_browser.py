"""Keep and control the exact Chromium used by the agent, via local CDP."""
import asyncio
import base64
import time
from pathlib import Path

from fastapi import HTTPException

VISUAL_SCRIPT = Path(__file__).with_name("visual_feedback.js").read_text(encoding="utf-8")


class LiveBrowser:
    def __init__(self, browser):
        self.browser = browser
        self.playwright = None
        self.connection = None
        self.chooser = None
        self.frame = None
        self.last_seen = time.monotonic()
        self.last_capture = 0.0
        self.last_control = None
        self.page_ids = {}
        self.lock = asyncio.Lock()
        self.actions = asyncio.Lock()

    async def connect(self):
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        self.connection = await self.playwright.chromium.connect_over_cdp(self.browser.cdp_url)
        for context in self.connection.contexts:
            await context.add_init_script(VISUAL_SCRIPT)
            context.on("page", self._attach)
            for page in context.pages:
                self._attach(page)
                await page.evaluate(VISUAL_SCRIPT)

    def _attach(self, page):
        page.on("filechooser", self._choose)

    def _choose(self, chooser):
        self.chooser = chooser

    async def page(self):
        # Agent focus can move to another tab. Match its current target, not a copy.
        target = await self.browser.get_current_target_info()
        if target:
            for context in self.connection.contexts:
                for page in reversed(context.pages):
                    if page.is_closed():
                        self.page_ids.pop(page, None)
                        continue
                    if page not in self.page_ids:
                        cdp = await context.new_cdp_session(page)
                        try:
                            info = await cdp.send("Target.getTargetInfo")
                            self.page_ids[page] = info["targetInfo"]["targetId"]
                        finally:
                            await cdp.detach()
                    if self.page_ids[page] == target["targetId"]:
                        return page
        raise HTTPException(status_code=410, detail="浏览器页面已关闭，请重新打开申请")

    async def capture(self, agent_running: bool):
        self.last_seen = time.monotonic()
        async with self.lock:
            if self.frame and self.last_control == agent_running and time.monotonic() - self.last_capture < .35:
                return self.frame
            page = await self.page()
            await page.evaluate("enabled => window.__questAgentVisual?.setEnabled(enabled)", agent_running)
            info = await page.evaluate("""() => ({width:innerWidth,height:innerHeight,
                target:window.__questAgentVisual?.events.at(-1)?.label || null,
                cursor:window.__questAgentVisual?.cursor || null,
                activity:window.__questAgentVisual?.events || []})""")
            image = await page.screenshot(type="jpeg", quality=70, timeout=5000)
            self.frame = {**info, "image": base64.b64encode(image).decode("ascii"),
                          "file_chooser": self.chooser is not None}
            self.last_capture = time.monotonic()
            self.last_control = agent_running
            return self.frame

    async def act(self, action, value):
        async with self.actions:
            self.last_seen = time.monotonic()
            page = await self.page()
            if action == "click_point":
                value = value or {}
                await page.mouse.click(float(value.get("x", 0)), float(value.get("y", 0)))
            elif action == "wheel":
                value = value or {}
                await page.mouse.wheel(float(value.get("delta_x", 0)), float(value.get("delta_y", 0)))
            elif action == "type":
                await page.keyboard.insert_text(str(value or ""))
            elif action == "key":
                await page.keyboard.press(str(value))
            elif action == "cancel_upload":
                self.chooser = None
            else:
                raise HTTPException(status_code=422, detail="不支持的浏览器操作")
            self.last_capture = 0

    async def upload(self, filename, content_type, content):
        async with self.actions:
            if not self.chooser:
                raise HTTPException(status_code=409, detail="请先点击业务页面的选择文件按钮")
            await self.chooser.set_files({"name": Path(filename).name, "mimeType": content_type,
                                          "buffer": content}, timeout=10000)
            self.chooser = None
            self.last_capture = 0

    async def close(self):
        if self.playwright:
            await self.playwright.stop()
        await self.browser.kill()
