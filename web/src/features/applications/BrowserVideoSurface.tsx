import { useEffect, useRef, type KeyboardEvent, type PointerEvent } from "react";
import { createBrowserWebRtcOffer } from "../../api";

export function BrowserVideoSurface({ sessionId, onReady }: { sessionId: string; onReady?: (send: (message: unknown) => void) => void }) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const channelRef = useRef<RTCDataChannel | null>(null);
  useEffect(() => {
    let active = true;
    const pc = new RTCPeerConnection();
    pc.addTransceiver("video", { direction: "recvonly" });
    pc.ontrack = (event) => { if (videoRef.current) videoRef.current.srcObject = event.streams[0]; };
    void (async () => {
      const channel = pc.createDataChannel("browser-control");
      channelRef.current = channel;
      onReady?.((message) => { if (channel.readyState === "open") channel.send(JSON.stringify(message)); });
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      const answer = await createBrowserWebRtcOffer(sessionId, { type: offer.type, sdp: offer.sdp });
      if (active) await pc.setRemoteDescription(answer);
    })();
    return () => { active = false; channelRef.current?.close(); pc.close(); };
  }, [sessionId, onReady]);
  function send(message: unknown) { if (channelRef.current?.readyState === "open") channelRef.current.send(JSON.stringify(message)); }
  function pointer(event: PointerEvent<HTMLVideoElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    send({ action: "click_point", value: { x: event.nativeEvent.offsetX * 1280 / rect.width, y: event.nativeEvent.offsetY * 900 / rect.height } });
  }
  function key(event: KeyboardEvent<HTMLVideoElement>) {
    event.preventDefault();
    send({ action: event.key.length === 1 ? "type" : "key", value: event.key });
  }
  return <video ref={videoRef} autoPlay playsInline muted tabIndex={0} onPointerDown={pointer} onKeyDown={key} onWheel={(event) => send({ action: "wheel", value: { delta_x: event.deltaX, delta_y: event.deltaY } })} style={{ width: "100%", maxHeight: 680, background: "#111", cursor: "pointer" }} />;
}
