"""WebRTC video transport for generic Playwright browser sessions."""
import asyncio
import io
import json
from typing import Any

import numpy as np
from av import VideoFrame
from fastapi import HTTPException

from quest_rag.applications.playwright_runtime import runtime


class PageVideoTrack:
    kind = "video"

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._pts = 0

    async def recv(self):
        from aiortc import VideoStreamTrack
        # This object is replaced by _Track below; kept as a named contract.
        raise NotImplementedError


def make_track(session_id: str):
    from aiortc import VideoStreamTrack
    class _Track(VideoStreamTrack):
        async def recv(self):
            page = runtime._pages.get(session_id)
            if not page:
                raise HTTPException(status_code=404, detail="浏览器会话不存在")
            image = await page.screenshot(type="png")
            from PIL import Image
            array = np.asarray(Image.open(io.BytesIO(image)).convert("RGB"))
            frame = VideoFrame.from_ndarray(array, format="rgb24")
            frame.pts, frame.time_base = await self.next_timestamp()
            return frame
    return _Track()


class WebRtcRuntime:
    def __init__(self):
        self.connections: dict[str, Any] = {}

    async def offer(self, session_id: str, offer: dict) -> dict:
        if session_id not in runtime._pages:
            raise HTTPException(status_code=404, detail="浏览器会话不存在")
        from aiortc import RTCPeerConnection, RTCSessionDescription
        pc = RTCPeerConnection()
        self.connections[session_id] = pc
        pc.addTrack(make_track(session_id))

        @pc.on("datachannel")
        def on_datachannel(channel):
            @channel.on("message")
            async def on_message(message):
                try:
                    payload = json.loads(message)
                    if payload.get("action"):
                        await runtime.act(session_id, payload["action"], payload.get("target", ""), payload.get("value"))
                except (ValueError, TypeError):
                    return

        await pc.setRemoteDescription(RTCSessionDescription(sdp=offer["sdp"], type=offer["type"]))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

    async def close(self, session_id: str):
        pc = self.connections.pop(session_id, None)
        if pc:
            await pc.close()


webrtc_runtime = WebRtcRuntime()
