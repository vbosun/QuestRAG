import { Alert, App, Button, Modal, Spin, Space, Steps, Tag, Typography } from "antd";
import { PushpinOutlined } from "@ant-design/icons";
import React from "react";
import { useEffect, useRef, useState } from "react";
import { cancelApplicationBrowserUse, connectApplicationBrowser, getApplicationBrowserUseStatus, getApplicationCase, startApplicationBrowserUse } from "../../api";
import { BrowserVideoSurface } from "./BrowserVideoSurface";
import type { ApplicationDetail } from "./types";

const { Text } = Typography;

export function ApplicationFormDialog({ caseId, title, open, onClose }: { caseId: string; title: string; open: boolean; onClose: () => void }) {
  const { message } = App.useApp();
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [browserReady, setBrowserReady] = useState(false);
  const [browserUse, setBrowserUse] = useState<{ status: string; events: Array<{ kind: string; message: string; at: string }>; result?: string | null; error?: string | null }>({ status: "idle", events: [] });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [fillStage, setFillStage] = useState<"reading" | "filled" | "empty" | "failed">("reading");
  const [submissionMessage, setSubmissionMessage] = useState("");
  const [embeddedMissing, setEmbeddedMissing] = useState<string[] | null>(null);
  const [pinned, setPinned] = useState(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const dragState = useRef<{ startX: number; startY: number; originX: number; originY: number } | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      if (!open) return;
      setLoading(true);
      setLoadError("");
      setDetail(null);
      setBrowserReady(false);
      setBrowserUse({ status: "idle", events: [] });
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
            if (active) setBrowserUse({ status: task.status, events: task.events });
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
    if (!open || detail?.execution_mode !== "browser_use" || !["queued", "running"].includes(browserUse.status)) return;
    let active = true;
    const timer = window.setInterval(async () => {
      try {
        const latest = await getApplicationBrowserUseStatus(caseId);
        if (active) setBrowserUse(latest);
      } catch (error) {
        if (active) setBrowserUse((current) => ({ ...current, status: "failed", error: error instanceof Error ? error.message : "读取 Browser Use 状态失败" }));
      }
    }, 900);
    return () => { active = false; window.clearInterval(timer); };
  }, [browserUse.status, caseId, detail?.execution_mode, open]);

  useEffect(() => {
    function onEmbeddedSubmit(event: MessageEvent) {
      if (!open || event.origin !== mockBusinessOrigin() || event.source !== iframeRef.current?.contentWindow) return;
      if (event.data?.type === "agent-form-applied") {
        setFillStage(event.data.applied_count > 0 ? "filled" : "empty");
        if (Array.isArray(event.data.missing_required_labels)) setEmbeddedMissing(event.data.missing_required_labels);
        return;
      }
      if (event.data?.type !== "mock-business-submitted") return;
      setSubmissionMessage(event.data.message || "模拟业务系统已收到提交。");
      message.success(event.data.message || "独立业务系统已收到提交。");
    }
    window.addEventListener("message", onEmbeddedSubmit);
    return () => window.removeEventListener("message", onEmbeddedSubmit);
  }, [message, open]);

  useEffect(() => {
    if (!open || !detail || detail.execution_mode === "playwright" || fillStage !== "reading") return;
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
    if (!open || !pinned) return;
    const previousOverflow = document.body.style.overflow;
    const previousPaddingRight = document.body.style.paddingRight;
    document.body.style.overflow = "auto";
    document.body.style.paddingRight = "";
    return () => {
      document.body.style.overflow = previousOverflow;
      document.body.style.paddingRight = previousPaddingRight;
    };
  }, [open, pinned]);

  useEffect(() => {
    function move(event: PointerEvent) {
      if (!dragState.current) return;
      setPosition({
        x: dragState.current.originX + event.clientX - dragState.current.startX,
        y: dragState.current.originY + event.clientY - dragState.current.startY,
      });
    }
    function stop() { dragState.current = null; }
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    return () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", stop); };
  }, []);

  function beginDrag(event: React.PointerEvent<HTMLDivElement>) {
    if (!pinned || event.button !== 0) return;
    dragState.current = { startX: event.clientX, startY: event.clientY, originX: position.x, originY: position.y };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  const currentStep = detail ? Math.max(0, detail.definition.steps.findIndex((step) => step.code === detail.current_step)) : 0;
  const externalPageUrl = detail ? buildMockBusinessPageUrl(detail) : "";
  const isBrowserUse = detail?.execution_mode === "browser_use";
  const browserUseRunning = ["queued", "running"].includes(browserUse.status);
  const latestBrowserUseEvent = browserUse.events[browserUse.events.length - 1];
  const missing = embeddedMissing ?? (detail ? [
    ...detail.fields.filter((field) => field.required && (field.value === null || field.value === undefined || field.value === "")).map((field) => field.label),
    ...detail.materials.filter((material) => material.required && material.status !== "uploaded").map((material) => material.label),
  ] : []);
  const autoFailed = isBrowserUse && ["failed", "cancelled"].includes(browserUse.status);
  const bannerType = submissionMessage ? "success" : autoFailed || fillStage === "failed" ? "warning" : browserUseRunning || fillStage === "reading" ? "info" : missing.length ? "warning" : "success";
  const bannerMessage = submissionMessage || (autoFailed ? "自动填写未完成，您可以继续在下方表单核对和手动填写。" : browserUseRunning ? "自动填写正在执行，请等待结果后核对信息。" : isBrowserUse && browserUse.status === "completed" ? "自动填写任务已结束，请核对实际填写结果；下方为独立业务表单。" : fillStage === "failed" ? "尚未收到表单填写回执，请检查业务页面是否可用；不能确认信息已带入。" : fillStage === "reading" ? "正在连接业务页面并带入已有信息…" : fillStage === "empty" ? "暂无可自动带入的信息，请在下方填写申请。" : `业务页面已接收已有信息，请核对${missing.length ? `并补充：${missing.join("、")}` : "后提交"}。`);
  return <Modal
    rootClassName={pinned ? "application-modal-pinned" : ""}
    style={pinned ? { transform: `translate(${position.x}px, ${position.y}px)` } : undefined}
    open={open}
    onCancel={onClose}
    maskClosable={!pinned}
    keyboard={!pinned}
    footer={null}
    width={1000}
    destroyOnHidden
    title={<div className="application-modal-titlebar" onPointerDown={beginDrag}><Space><span>{title}</span><Tag color="cyan">Agent 已发起</Tag><Button size="small" type={pinned ? "primary" : "text"} icon={<PushpinOutlined />} onPointerDown={(event) => event.stopPropagation()} onClick={() => setPinned((value) => !value)}>{pinned ? "取消固定" : "固定在对话上方"}</Button></Space></div>}
  >
    {loading ? <div className="application-dialog-loading"><Spin /></div> : loadError ? <Alert type="error" showIcon message="申请页面读取失败" description={loadError} /> : !detail ? null : <div className="application-dialog">
      <Alert type={bannerType} showIcon message={bannerMessage} description={detail.execution_notice || undefined} />
      <Steps size="small" current={currentStep} items={detail.definition.steps.map((step) => ({ title: step.name }))} />
      <div className="embedded-business-page">
        <div className="embedded-business-toolbar"><Tag color={detail.execution_mode === "playwright" ? "blue" : isBrowserUse ? "purple" : "green"}>{detail.execution_mode === "playwright" ? "Playwright 实时浏览器页面" : isBrowserUse ? "Browser Use 自治操作" : "外部业务系统页面"}</Tag><Text type="secondary">{detail.execution_mode === "playwright" ? "Agent 通过受控浏览器观察并操作，过程实时展示" : isBrowserUse ? "Agent 在独立受控浏览器中执行已确认的填写步骤；此页面仍可由您直接核对和修改，不会跳转" : "页面已嵌入当前对话，Agent 和您都在这里操作，不会跳转"}</Text>{isBrowserUse && browserUseRunning ? <Button size="small" onClick={() => void cancelApplicationBrowserUse(caseId).then(() => setBrowserUse((current) => ({ ...current, status: "cancelled" }))).catch((error) => message.error(error instanceof Error ? error.message : "停止失败"))}>停止 Agent</Button> : null}</div>
        {detail.execution_mode === "playwright" ? (
          <div className="playwright-page-preview">
            {browserReady ? <BrowserVideoSurface sessionId={caseId} /> : <Spin />}
            <Text type="secondary">这是后端 Playwright 的连续视频画面。点击视频后可直接操作页面，键盘输入和滚轮事件会回传到同一浏览器会话。</Text>
          </div>
        ) : <iframe ref={iframeRef} title={`${title}业务页面`} src={externalPageUrl} onLoad={() => sendFieldsToEmbeddedPage(detail, iframeRef.current)} />}
      </div>
      {isBrowserUse ? <div className="browser-use-task-status" aria-live="polite">
        <Space size="small"><Tag color={browserUse.status === "completed" ? "success" : browserUse.status === "failed" ? "error" : browserUse.status === "cancelled" ? "default" : "processing"}>{browserUse.status === "queued" ? "等待执行" : browserUse.status === "running" ? "正在操作" : browserUse.status === "completed" ? "操作完成" : browserUse.status === "cancelled" ? "已停止" : browserUse.status === "idle" ? "准备执行" : "执行异常"}</Tag><Text type="secondary">{latestBrowserUseEvent?.message || "正在准备 Agent 操作"}</Text></Space>
        {browserUse.events.length > 1 ? <div className="browser-use-events">{browserUse.events.map((event) => <div key={`${event.at}-${event.kind}`}>• {event.message}</div>)}</div> : null}
        {browserUse.error ? <Text type="danger">{browserUse.error}</Text> : null}
      </div> : null}
    </div>}
  </Modal>;
}

function sendFieldsToEmbeddedPage(detail: ApplicationDetail | null, frame: HTMLIFrameElement | null) {
  if (!detail || !frame?.contentWindow) return;
  const fields = Object.fromEntries(detail.fields.filter((field) => field.value !== null && field.value !== undefined).map((field) => [field.key, field.value]));
  frame.contentWindow.postMessage({ type: "agent-form-state", fields }, mockBusinessOrigin());
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
