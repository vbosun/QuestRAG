import { Alert, App, Button, Modal, Spin, Space, Steps, Tag, Typography } from "antd";
import React from "react";
import { useEffect, useRef, useState } from "react";
import { cancelApplicationBrowserUse, connectApplicationBrowser, getApplicationBrowserUseStatus, getApplicationCase, startApplicationBrowserUse, syncApplicationPage } from "../../api";
import { createClientId } from "../../clientId";
import { BrowserVideoSurface } from "./BrowserVideoSurface";
import type { BrowserUseState } from "../../api";
import type { ApplicationDetail } from "./types";

const { Text } = Typography;

type WindowBounds = { x: number; y: number; width: number; height: number };

function fitWindow(bounds: WindowBounds): WindowBounds {
  const availableWidth = Math.max(1, window.innerWidth - 32);
  const availableHeight = Math.max(1, window.innerHeight - 32);
  const width = Math.min(availableWidth, Math.max(Math.min(520, availableWidth), bounds.width));
  const height = Math.min(availableHeight, Math.max(Math.min(360, availableHeight), bounds.height));
  return { width, height, x: Math.max(16, Math.min(bounds.x, window.innerWidth - width - 16)),
    y: Math.max(16, Math.min(bounds.y, window.innerHeight - height - 16)) };
}

function initialWindow(): WindowBounds {
  const width = Math.min(1000, window.innerWidth - 32);
  const height = Math.min(780, Math.max(380, window.innerHeight - 230));
  return fitWindow({ x: (window.innerWidth - width) / 2, y: 76, width, height });
}

export function ApplicationFormDialog({ caseId, title, open, onClose }: { caseId: string; title: string; open: boolean; onClose: () => void }) {
  const { message } = App.useApp();
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [browserReady, setBrowserReady] = useState(false);
  const [browserUse, setBrowserUse] = useState<BrowserUseState>({ status: "idle", events: [] });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [fillStage, setFillStage] = useState<"reading" | "filled" | "empty" | "failed">("reading");
  const [submissionMessage, setSubmissionMessage] = useState("");
  const [embeddedMissing, setEmbeddedMissing] = useState<string[] | null>(null);
  const [bounds, setBounds] = useState<WindowBounds>(initialWindow);
  const [interacting, setInteracting] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const takeoverRef = useRef(false);
  const stoppedTaskRef = useRef<string | undefined>(undefined);
  const pageIdRef = useRef(createClientId());
  const lastSnapshotRef = useRef<Parameters<typeof syncApplicationPage>[1] | null>(null);
  const syncQueueRef = useRef<Promise<unknown>>(Promise.resolve());
  const [pageSyncError, setPageSyncError] = useState("");
  const [takingOver, setTakingOver] = useState(false);
  const dragState = useRef<{ mode: "move" | "resize"; pointerId: number; startX: number; startY: number; bounds: WindowBounds } | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      if (!open) return;
      setLoading(true);
      setLoadError("");
      setDetail(null);
      setBrowserReady(false);
      setBrowserUse({ status: "idle", events: [] });
      takeoverRef.current = false;
      stoppedTaskRef.current = undefined;
      pageIdRef.current = createClientId();
      lastSnapshotRef.current = null;
      setPageSyncError("");
      setTakingOver(false);
      setFillStage("reading");
      setSubmissionMessage("");
      setEmbeddedMissing(null);
      try {
        const result = await getApplicationCase(caseId);
        if (!active) return;
        setDetail(result);
        if (result.execution_mode === "playwright") {
          try {
            await connectApplicationBrowser(caseId);
            if (active) { setBrowserReady(true); setFillStage("filled"); }
          } catch (error) {
            if (active) { setFillStage("failed"); message.warning(error instanceof Error ? error.message : "浏览器连接失败"); }
          }
        }
        if (result.execution_mode === "browser_use") {
          try {
            const task = await startApplicationBrowserUse(caseId);
            if (active) setBrowserUse(task);
          } catch (error) {
            if (active) setBrowserUse({ status: "failed", events: [], error: error instanceof Error ? error.message : "Browser Use 启动失败" });
          }
        }
      } catch (error) {
        if (active) setLoadError(error instanceof Error ? error.message : "读取申请页面失败");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, [caseId, message, open]);

  useEffect(() => {
    if (!open || detail?.execution_mode !== "browser_use") return;
    let active = true;
    let busy = false;
    const timer = window.setInterval(async () => {
      if (busy) return;
      busy = true;
      try {
        const latest = await getApplicationBrowserUseStatus(caseId);
        if (active && (!takeoverRef.current || (latest.task_id && latest.task_id !== stoppedTaskRef.current))) {
          if (latest.task_id !== stoppedTaskRef.current) takeoverRef.current = false;
          setBrowserUse((current) => JSON.stringify(current) === JSON.stringify(latest) ? current : latest);
        }
      } catch (error) {
        if (active && !takeoverRef.current) setBrowserUse((current) => ({ ...current, view_error: error instanceof Error ? error.message : "操作状态连接暂时中断" }));
      } finally {
        busy = false;
      }
    }, 500);
    return () => { active = false; window.clearInterval(timer); };
  }, [caseId, detail?.execution_mode, open]);

  useEffect(() => {
    if (open && detail?.execution_mode === "browser_use") sendBrowserUseProgress(browserUse, iframeRef.current);
  }, [browserUse, detail?.execution_mode, open]);

  useEffect(() => {
    function onEmbeddedSubmit(event: MessageEvent) {
      if (!open || event.origin !== mockBusinessOrigin() || event.source !== iframeRef.current?.contentWindow) return;
      if (event.data?.type === "agent-form-applied") {
        setFillStage(event.data.applied_count > 0 ? "filled" : "empty");
        if (Array.isArray(event.data.missing_required_labels)) setEmbeddedMissing(event.data.missing_required_labels);
        if (detail?.execution_mode === "browser_use" && event.data.page_id === pageIdRef.current && event.data.fields) {
          const snapshot = { page_id: event.data.page_id, sequence: event.data.sequence, open: true,
            fields: event.data.fields, field_revisions: event.data.field_revisions || {}, task_id: event.data.task_id,
            conflicts: event.data.conflicts || [], submitted: Boolean(event.data.submitted) };
          lastSnapshotRef.current = snapshot;
          syncQueueRef.current = syncQueueRef.current.catch(() => {}).then(() => syncApplicationPage(caseId, snapshot))
            .then(() => setPageSyncError(""), () => setPageSyncError("表单状态同步暂时中断，聊天填写将在连接恢复后可用。"));
        }
        return;
      }
      if (event.data?.type !== "mock-business-submitted") return;
      setSubmissionMessage(event.data.message || "模拟业务系统已收到提交。");
      message.success(event.data.message || "独立业务系统已收到提交。");
    }
    window.addEventListener("message", onEmbeddedSubmit);
    return () => window.removeEventListener("message", onEmbeddedSubmit);
  }, [caseId, detail?.execution_mode, message, open]);

  useEffect(() => {
    if (!open || detail?.execution_mode !== "browser_use") return;
    const requestSnapshot = () => iframeRef.current?.contentWindow?.postMessage({ type: "agent-form-snapshot-request", page_id: pageIdRef.current }, mockBusinessOrigin());
    requestSnapshot();
    const timer = window.setInterval(requestSnapshot, 1000);
    return () => {
      window.clearInterval(timer);
      const snapshot = lastSnapshotRef.current;
      if (snapshot) syncQueueRef.current = syncQueueRef.current.catch(() => {}).then(() => syncApplicationPage(caseId, { ...snapshot, sequence: snapshot.sequence + 1, open: false })).catch(() => {});
    };
  }, [caseId, detail?.execution_mode, open]);

  useEffect(() => {
    if (!open || !detail || detail.execution_mode !== "embedded" || fillStage !== "reading") return;
    const timer = window.setTimeout(() => setFillStage("failed"), 10000);
    return () => window.clearTimeout(timer);
  }, [detail?.id, detail?.execution_mode, fillStage, open]);

  useEffect(() => {
    if (!open || !detail) return;
    let active = true;
    const timer = window.setInterval(async () => {
      try {
        const latest = await getApplicationCase(caseId);
        if (!active) return;
        setDetail(latest);
        sendFieldsToEmbeddedPage(latest, iframeRef.current);
      } catch {
        // The embedded business system may be temporarily unavailable; keep the chat usable.
      }
    }, 1800);
    return () => { active = false; window.clearInterval(timer); };
  }, [caseId, detail?.id, open]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    const previousPaddingRight = document.body.style.paddingRight;
    document.body.style.overflow = "auto";
    document.body.style.paddingRight = "";
    return () => {
      document.body.style.overflow = previousOverflow;
      document.body.style.paddingRight = previousPaddingRight;
    };
  }, [open]);

  useEffect(() => {
    function move(event: PointerEvent) {
      const gesture = dragState.current;
      if (!gesture || gesture.pointerId !== event.pointerId) return;
      const dx = event.clientX - gesture.startX;
      const dy = event.clientY - gesture.startY;
      setBounds(fitWindow(gesture.mode === "move"
        ? { ...gesture.bounds, x: gesture.bounds.x + dx, y: gesture.bounds.y + dy }
        : { ...gesture.bounds, width: Math.min(gesture.bounds.width + dx, window.innerWidth - gesture.bounds.x - 16),
          height: Math.min(gesture.bounds.height + dy, window.innerHeight - gesture.bounds.y - 16) }));
    }
    function stop() { dragState.current = null; setInteracting(false); }
    function resizeViewport() { stop(); setBounds((current) => fitWindow(current)); }
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    window.addEventListener("resize", resizeViewport);
    return () => {
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop); window.removeEventListener("resize", resizeViewport);
    };
  }, []);

  useEffect(() => {
    dragState.current = null;
    setInteracting(false);
    if (open) setBounds((current) => fitWindow(current));
  }, [open]);

  function beginGesture(event: React.PointerEvent<HTMLElement>, mode: "move" | "resize") {
    if (event.button !== 0 || !event.isPrimary) return;
    event.preventDefault();
    event.stopPropagation();
    dragState.current = { mode, pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, bounds };
    setInteracting(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function beginDrag(event: React.PointerEvent<HTMLDivElement>) {
    if ((event.target as HTMLElement).closest("button, a, input")) return;
    beginGesture(event, "move");
  }

  function adjustWithKeyboard(event: React.KeyboardEvent<HTMLButtonElement>, mode: "move" | "resize") {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    event.preventDefault();
    const distance = event.shiftKey ? 40 : 10;
    const dx = event.key === "ArrowLeft" ? -distance : event.key === "ArrowRight" ? distance : 0;
    const dy = event.key === "ArrowUp" ? -distance : event.key === "ArrowDown" ? distance : 0;
    setBounds((current) => fitWindow(mode === "move"
      ? { ...current, x: current.x + dx, y: current.y + dy }
      : { ...current, width: Math.min(current.width + dx, window.innerWidth - current.x - 16),
        height: Math.min(current.height + dy, window.innerHeight - current.y - 16) }));
  }

  async function takeOver() {
    takeoverRef.current = true;
    stoppedTaskRef.current = browserUse.task_id;
    setTakingOver(true);
    try {
      setBrowserUse(await cancelApplicationBrowserUse(caseId));
    } catch (error) {
      takeoverRef.current = false;
      message.error(error instanceof Error ? error.message : "停止失败，请重试");
    } finally {
      setTakingOver(false);
    }
  }

  const currentStep = detail ? Math.max(0, detail.definition.steps.findIndex((step) => step.code === detail.current_step)) : 0;
  const externalPageUrl = detail ? buildMockBusinessPageUrl(detail) : "";
  const isBrowserUse = detail?.execution_mode === "browser_use";
  const browserUseRunning = ["queued", "running"].includes(browserUse.status);
  const completionLabel = browserUse.command_id && browserUse.page_sync?.status !== "applied"
    ? browserUse.page_sync?.status === "conflict" ? "保留手动修改" : "后台执行结束" : "操作完成";
  const latestBrowserUseEvent = browserUse.events[browserUse.events.length - 1];
  const operations = browserUse.operation_events || [];
  const latestOperation = operations[operations.length - 1];
  const missing = embeddedMissing ?? (detail ? [
    ...detail.fields.filter((field) => field.required && (field.value === null || field.value === undefined || field.value === "")).map((field) => field.label),
    ...detail.materials.filter((material) => material.required && material.status !== "uploaded").map((material) => material.label),
  ] : []);
  const autoFailed = isBrowserUse && ["failed", "cancelled"].includes(browserUse.status);
  const bannerType = submissionMessage ? "success" : autoFailed || fillStage === "failed" ? "warning" : browserUseRunning || fillStage === "reading" ? "info" : missing.length ? "warning" : "success";
  const bannerMessage = submissionMessage || (isBrowserUse ? (browserUseRunning ? "AI 正在填写，高亮位置对应当前操作；您可以随时停止并接手填写。" : browserUse.status === "completed" ? "自动填写已结束，请核对同步结果、补充材料后自行提交。" : autoFailed ? "自动填写已停止，已同步的信息会保留，您可以继续手动填写。" : "正在准备自动填写…") : fillStage === "failed" ? "尚未收到表单填写回执，请检查业务页面是否可用；不能确认信息已带入。" : fillStage === "reading" ? "正在连接业务页面并带入已有信息…" : fillStage === "empty" ? "暂无可自动带入的信息，请在下方填写申请。" : `业务页面已接收已有信息，请核对${missing.length ? `并补充：${missing.join("、")}` : "后提交"}。`);
  return <Modal
    rootClassName="application-modal-floating"
    style={{ left: bounds.x, top: bounds.y, height: bounds.height }}
    open={open}
    onCancel={onClose}
    mask={false}
    keyboard={!isBrowserUse}
    footer={null}
    width={bounds.width}
    destroyOnHidden
    title={<div className="application-modal-titlebar" onPointerDown={beginDrag}><Space wrap><span>{title}</span><Tag color="cyan">Agent 已发起</Tag></Space></div>}
    modalRender={(modal) => <div className={`application-window-frame${interacting ? " is-interacting" : ""}`} style={{ height: bounds.height }}>
      {modal}
      <button type="button" className="application-window-handle application-window-move" aria-label="拖动申请页面" title="拖动移动；方向键微调位置"
        onPointerDown={(event) => beginGesture(event, "move")} onLostPointerCapture={() => { dragState.current = null; setInteracting(false); }} onKeyDown={(event) => adjustWithKeyboard(event, "move")}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="6" r="1.5" /><circle cx="15" cy="6" r="1.5" /><circle cx="9" cy="12" r="1.5" /><circle cx="15" cy="12" r="1.5" /><circle cx="9" cy="18" r="1.5" /><circle cx="15" cy="18" r="1.5" /></svg>
      </button>
      <button type="button" className="application-window-handle application-window-resize" aria-label="调整申请页面大小" title="拖动调整大小；方向键微调"
        onPointerDown={(event) => beginGesture(event, "resize")} onLostPointerCapture={() => { dragState.current = null; setInteracting(false); }} onKeyDown={(event) => adjustWithKeyboard(event, "resize")}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="8" cy="16" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="16" cy="8" r="1.5" /><circle cx="12" cy="18" r="1.5" /><circle cx="18" cy="12" r="1.5" /><circle cx="18" cy="18" r="1.5" /></svg>
      </button>
    </div>}
  >
    {loading ? <div className="application-dialog-loading"><Spin /></div> : loadError ? <Alert type="error" showIcon message="申请页面读取失败" description={loadError} /> : !detail ? null : <div className="application-dialog">
      <Alert type={bannerType} showIcon message={bannerMessage} description={isBrowserUse ? undefined : detail.execution_notice || undefined} />
      <Steps size="small" current={currentStep} items={detail.definition.steps.map((step) => ({ title: step.name }))} />
      <div className="embedded-business-page">
        <div className="embedded-business-toolbar"><Tag color={detail.execution_mode === "playwright" ? "blue" : isBrowserUse ? "purple" : "green"}>{detail.execution_mode === "playwright" ? "Playwright 实时浏览器页面" : "业务表单"}</Tag><Text type="secondary">{detail.execution_mode === "playwright" ? "Agent 通过受控浏览器观察并操作，过程实时展示" : isBrowserUse ? "AI 填写结果同步到表单，您可直接核对和修改" : "页面已嵌入当前对话，可直接核对和填写"}</Text>{isBrowserUse && browserUseRunning ? <Button size="small" loading={takingOver} onClick={() => void takeOver()}>停止并接管</Button> : null}</div>
        {detail.execution_mode === "playwright" ? (
          <div className="playwright-page-preview">
            {browserReady ? <BrowserVideoSurface sessionId={caseId} /> : <Spin />}
            <Text type="secondary">这是后端 Playwright 的连续视频画面。点击视频后可直接操作页面，键盘输入和滚轮事件会回传到同一浏览器会话。</Text>
          </div>
        ) : <iframe ref={iframeRef} title={`${title}业务页面`} src={externalPageUrl} onLoad={() => {
          sendFieldsToEmbeddedPage(detail, iframeRef.current);
          if (isBrowserUse) {
            if (detail.page_fields) iframeRef.current?.contentWindow?.postMessage({ type: "agent-form-restore", fields: detail.page_fields }, mockBusinessOrigin());
            iframeRef.current?.contentWindow?.postMessage({ type: "agent-form-snapshot-request", page_id: pageIdRef.current }, mockBusinessOrigin());
          }
          if (isBrowserUse) sendBrowserUseProgress(browserUse, iframeRef.current);
        }} />}
      </div>
      {isBrowserUse ? <div className="browser-use-task-status" aria-live="polite">
        <Space size="small"><Tag color={browserUse.status === "completed" ? completionLabel === "操作完成" ? "success" : "warning" : browserUse.status === "failed" ? "error" : browserUse.status === "cancelled" ? "default" : "processing"}>{browserUse.status === "queued" ? "等待执行" : browserUse.status === "running" ? "正在操作" : browserUse.status === "completed" ? completionLabel : browserUse.status === "cancelled" ? "已停止" : browserUse.status === "idle" ? "准备执行" : "执行异常"}</Tag><Text type="secondary">{browserUseRunning && latestOperation ? `AI 操作目标：${latestOperation.label}` : latestBrowserUseEvent?.message || "正在准备页面"}</Text></Space>
        {browserUse.events.length > 1 ? <div className="browser-use-events">{browserUse.events.map((event) => <div key={`${event.at}-${event.kind}`}>• {event.message}</div>)}</div> : null}
        {browserUse.error ? <Text type="danger">{browserUse.error}</Text> : null}
        {browserUse.view_error ? <Text type="warning">{browserUse.view_error}</Text> : null}
        {pageSyncError ? <Text type="warning">{pageSyncError}</Text> : null}
      </div> : null}
    </div>}
  </Modal>;
}

function sendFieldsToEmbeddedPage(detail: ApplicationDetail | null, frame: HTMLIFrameElement | null) {
  if (!detail || !frame?.contentWindow) return;
  const fields = Object.fromEntries(detail.fields.filter((field) => field.value !== null && field.value !== undefined && (detail.execution_mode !== "browser_use" || !field.editable)).map((field) => [field.key, field.value]));
  frame.contentWindow.postMessage({ type: "agent-form-state", fields }, mockBusinessOrigin());
}

function sendBrowserUseProgress(state: BrowserUseState, frame: HTMLIFrameElement | null) {
  frame?.contentWindow?.postMessage({ type: "agent-form-progress", task_id: state.task_id, status: state.status,
    command_id: state.command_id, page_id: state.page_id, requested_fields: state.requested_fields, field_revisions: state.field_revisions,
    operations: state.operation_events || [], fields: state.form_fields || {} }, mockBusinessOrigin());
}

function buildMockBusinessPageUrl(detail: ApplicationDetail): string {
  const query = new URLSearchParams({ case_id: detail.id }).toString();
  const path = detail.business_code === "unemployment_registration" ? "unemployment-registration" : "employment-registration";
  return `${mockBusinessOrigin()}/${path}/apply${query ? `?${query}` : ""}`;
}

function mockBusinessOrigin(): string {
  const base = import.meta.env.VITE_MOCK_BUSINESS_BASE_URL ?? "http://127.0.0.1:8020";
  return new URL(base || window.location.origin, window.location.origin).origin;
}
