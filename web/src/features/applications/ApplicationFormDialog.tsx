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
  const [fillStage, setFillStage] = useState<"reading" | "filled">("reading");
  const [pinned, setPinned] = useState(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const dragState = useRef<{ startX: number; startY: number; originX: number; originY: number } | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      if (!open) return;
      try {
        const result = await getApplicationCase(caseId);
        if (!active) return;
        setDetail(result);
        if (result.execution_mode === "playwright") {
          try {
            await connectApplicationBrowser(caseId);
            if (active) setBrowserReady(true);
          } catch (error) {
            if (active) message.warning(error instanceof Error ? error.message : "Playwright 浏览器连接失败");
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
        window.setTimeout(() => active && setFillStage("filled"), 650);
      } catch (error) {
        message.error(error instanceof Error ? error.message : "读取申请页面失败");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, [caseId, message, open]);

  useEffect(() => {
    if (!open || detail?.execution_mode !== "browser_use" || !["queued", "running"].includes(browserUse.status)) return;
    const timer = window.setInterval(async () => {
      try {
        setBrowserUse(await getApplicationBrowserUseStatus(caseId));
      } catch (error) {
        setBrowserUse((current) => ({ ...current, status: "failed", error: error instanceof Error ? error.message : "读取 Browser Use 状态失败" }));
      }
    }, 900);
    return () => window.clearInterval(timer);
  }, [browserUse.status, caseId, detail?.execution_mode, open]);

  useEffect(() => {
    function onEmbeddedSubmit(event: MessageEvent) {
      if (event.data?.type !== "mock-business-submitted") return;
      setDetail((current) => current ? { ...current, status: "SUBMITTED", current_step: "user_confirmation", next_action: { code: "SUBMITTED", message: event.data.message || "独立业务系统已收到提交。" } } : current);
      message.success(event.data.message || "独立业务系统已收到提交。");
    }
    window.addEventListener("message", onEmbeddedSubmit);
    return () => window.removeEventListener("message", onEmbeddedSubmit);
  }, [message]);

  useEffect(() => {
    if (!open || !detail) return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await getApplicationCase(caseId);
        setDetail(latest);
        sendFieldsToEmbeddedPage(latest, iframeRef.current);
      } catch {
        // The embedded business system may be temporarily unavailable; keep the chat usable.
      }
    }, 1800);
    return () => window.clearInterval(timer);
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
    {loading || !detail ? <div className="application-dialog-loading"><Spin /></div> : <div className="application-dialog">
      <Alert type={fillStage === "reading" ? "info" : "success"} showIcon message={fillStage === "reading" ? "Agent 正在带入个人档案信息…" : "Agent 已完成可用信息带入，请直接在业务页面核对、修改或提交。"} />
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
        <Space size="small"><Tag color={browserUse.status === "completed" ? "success" : browserUse.status === "failed" ? "error" : browserUse.status === "cancelled" ? "default" : "processing"}>{browserUse.status === "queued" ? "等待执行" : browserUse.status === "running" ? "正在操作" : browserUse.status === "completed" ? "操作完成" : browserUse.status === "cancelled" ? "已停止" : "执行异常"}</Tag><Text type="secondary">{latestBrowserUseEvent?.message || "正在准备 Agent 操作"}</Text></Space>
        {browserUse.events.length > 1 ? <div className="browser-use-events">{browserUse.events.map((event) => <div key={`${event.at}-${event.kind}`}>• {event.message}</div>)}</div> : null}
        {browserUse.error ? <Text type="danger">{browserUse.error}</Text> : null}
      </div> : null}
    </div>}
  </Modal>;
}

function sendFieldsToEmbeddedPage(detail: ApplicationDetail | null, frame: HTMLIFrameElement | null) {
  if (!detail || !frame?.contentWindow) return;
  const fields = Object.fromEntries(detail.fields.filter((field) => field.value !== null && field.value !== undefined).map((field) => [field.key, field.value]));
  frame.contentWindow.postMessage({ type: "agent-form-state", fields }, "http://127.0.0.1:8020");
}

function buildMockBusinessPageUrl(detail: ApplicationDetail): string {
  const values = Object.fromEntries(detail.fields.filter((field) => field.value !== null && field.value !== undefined).map((field) => [field.key, String(field.value)]));
  const query = new URLSearchParams(values).toString();
  const path = detail.business_code === "unemployment_registration" ? "unemployment-registration" : "employment-registration";
  return `http://127.0.0.1:8020/${path}/apply${query ? `?${query}` : ""}`;
}
