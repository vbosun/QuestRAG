import { App, Button, Spin, Typography } from "antd";
import { useEffect, useRef, type KeyboardEvent } from "react";
import { actApplicationBrowserUse, uploadApplicationBrowserFile, type BrowserUseState } from "../../api";

export function BrowserUseSurface({ caseId, state, onState }: {
  caseId: string; state: BrowserUseState; onState: (state: BrowserUseState) => void;
}) {
  const { message } = App.useApp();
  const imageRef = useRef<HTMLImageElement>(null);
  const keyboardRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const surfaceRef = useRef<HTMLDivElement>(null);
  const composing = useRef(false);
  const queue = useRef(Promise.resolve());
  const canControl = state.control === "user" && state.page_available && !state.view_error;
  const controlRef = useRef(canControl);
  controlRef.current = canControl;

  function send(action: string, value?: unknown) {
    if (!controlRef.current) return;
    // Preserve click/type/key order even when the user types faster than the network.
    queue.current = queue.current.then(async () => {
      const latest = await actApplicationBrowserUse(caseId, action, value);
      onState(latest);
    }).catch((error) => { message.error(error instanceof Error ? error.message : "页面操作失败"); });
  }

  useEffect(() => {
    const surface = surfaceRef.current;
    if (!surface) return;
    function wheel(event: WheelEvent) {
      event.preventDefault();
      send("wheel", { delta_x: event.deltaX, delta_y: event.deltaY });
    }
    surface.addEventListener("wheel", wheel, { passive: false });
    return () => surface.removeEventListener("wheel", wheel);
  });

  function key(event: KeyboardEvent) {
    if (event.nativeEvent.isComposing || composing.current || !canControl) return;
    if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) return;
    if (["Shift", "Control", "Alt", "Meta", "Process", "Unidentified"].includes(event.key)) return;
    event.preventDefault(); event.stopPropagation();
    const modifiers = [event.ctrlKey || event.metaKey ? "Control" : "", event.altKey ? "Alt" : "", event.shiftKey ? "Shift" : ""].filter(Boolean);
    send("key", [...modifiers, event.key === " " ? "Space" : event.key].join("+"));
  }

  const frame = state.live_frame;
  return <div className="browser-use-surface">
    <div className="browser-use-screen" ref={surfaceRef} aria-busy={state.control === "agent"}>
      {frame ? <img ref={imageRef} src={`data:image/jpeg;base64,${frame.image}`} alt="当前业务浏览器页面" draggable={false}
        style={{ cursor: canControl ? "text" : "default" }}
        onClick={(event) => {
          if (!canControl) return;
          const rect = event.currentTarget.getBoundingClientRect();
          keyboardRef.current?.focus({ preventScroll: true });
          send("click_point", { x: (event.clientX - rect.left) * frame.width / rect.width, y: (event.clientY - rect.top) * frame.height / rect.height });
        }} /> : <div className="browser-use-connecting"><Spin /><span>{state.page_available ? "正在获取页面画面…" : ["queued", "running"].includes(state.status) ? "正在打开业务页面…" : "浏览器会话已结束，关闭后重新打开申请可恢复"}</span></div>}
      {frame?.cursor && state.control === "agent" ? <div className="browser-use-ai-pointer" aria-hidden="true"
        style={{ left: `${frame.cursor.x / frame.width * 100}%`, top: `${frame.cursor.y / frame.height * 100}%` }}>
        <svg width="25" height="31" viewBox="0 0 25 31"><path d="M2 2L3 25L9 19L14 29L19 26L14 16L23 15Z" fill="#12b8ae" stroke="white" strokeWidth="2" /></svg>
        <span>AI 操作中</span>
      </div> : null}
      <textarea ref={keyboardRef} className="browser-use-keyboard" aria-label="业务页面键盘输入" disabled={!canControl}
        onKeyDown={key}
        onCompositionStart={() => { composing.current = true; }}
        onCompositionEnd={(event) => { composing.current = false; send("type", event.data); event.currentTarget.value = ""; }}
        onChange={(event) => { if (!composing.current && event.currentTarget.value) { send("type", event.currentTarget.value); event.currentTarget.value = ""; } }}
        onPaste={(event) => { event.preventDefault(); send("type", event.clipboardData.getData("text/plain")); }} />
    </div>
    {state.view_error ? <Typography.Text type="warning">{state.view_error}，暂时无法操作。</Typography.Text> : null}
    {frame?.file_chooser && canControl ? <div className="browser-use-upload">
      <span>页面正在等待材料，请选择本机文件。</span>
      <Button onClick={() => fileRef.current?.click()}>选择材料</Button>
      <Button type="text" onClick={() => send("cancel_upload")}>取消</Button>
      <input ref={fileRef} type="file" hidden onChange={(event) => {
        const file = event.currentTarget.files?.[0]; event.currentTarget.value = "";
        if (!file) return;
        if (file.size > 10 * 1024 * 1024) { message.error("材料不能超过 10 MB"); return; }
        queue.current = queue.current.then(async () => onState(await uploadApplicationBrowserFile(caseId, file)))
          .catch((error) => { message.error(error instanceof Error ? error.message : "上传失败"); });
      }} />
    </div> : null}
  </div>;
}
