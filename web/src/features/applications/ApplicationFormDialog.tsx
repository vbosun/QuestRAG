import { Alert, App, Button, Modal, Spin, Space, Steps, Tag, Typography } from "antd";
import { PushpinOutlined } from "@ant-design/icons";
import React from "react";
import { useEffect, useRef, useState } from "react";
import { getApplicationCase } from "../../api";
import type { ApplicationDetail } from "./types";

const { Text } = Typography;

export function ApplicationFormDialog({ caseId, title, open, onClose }: { caseId: string; title: string; open: boolean; onClose: () => void }) {
  const { message } = App.useApp();
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [fillStage, setFillStage] = useState<"reading" | "filled">("reading");
  const [pinned, setPinned] = useState(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const dragState = useRef<{ startX: number; startY: number; originX: number; originY: number } | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const result = await getApplicationCase(caseId);
        if (!active) return;
        setDetail(result);
        window.setTimeout(() => active && setFillStage("filled"), 650);
      } catch (error) {
        message.error(error instanceof Error ? error.message : "读取申请页面失败");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, [caseId, message]);

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
        <div className="embedded-business-toolbar"><Tag color="green">外部业务系统页面</Tag><Text type="secondary">页面已嵌入当前对话，Agent 和您都在这里操作，不会跳转</Text></div>
        <iframe title={`${title}业务页面`} src={externalPageUrl} />
      </div>
    </div>}
  </Modal>;
}

function buildMockBusinessPageUrl(detail: ApplicationDetail): string {
  const values = Object.fromEntries(detail.fields.filter((field) => field.value !== null && field.value !== undefined).map((field) => [field.key, String(field.value)]));
  const query = new URLSearchParams(values).toString();
  return `http://127.0.0.1:8020/employment-registration/apply${query ? `?${query}` : ""}`;
}
