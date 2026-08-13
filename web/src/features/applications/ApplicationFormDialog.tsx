import { CheckCircleOutlined, GlobalOutlined, SafetyCertificateOutlined, SyncOutlined } from "@ant-design/icons";
import { Alert, App, Button, Descriptions, Form, Input, Modal, Select, Space, Spin, Steps, Tag, Timeline, Typography, Upload } from "antd";
import { useEffect, useState } from "react";
import { connectApplicationBrowser, getApplicationCase, submitApplication, syncApplicationDraft, updateApplicationDraftField, uploadApplicationMaterial } from "../../api";
import type { ApplicationDetail, ApplicationField } from "./types";

const { Text, Title } = Typography;

const SOURCE_LABELS: Record<string, string> = {
  user_manual: "用户填写", agent_suggested: "Agent 建议", profile_prefill: "个人档案带入",
  official_readonly: "官方只读", official_observed: "官方页面读取",
};

export function ApplicationFormDialog({ caseId, title, open, onClose }: { caseId: string; title: string; open: boolean; onClose: () => void }) {
  const { message } = App.useApp();
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [fillStage, setFillStage] = useState<"reading" | "filled">("reading");

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const result = await getApplicationCase(caseId);
        if (!active) return;
        setDetail(result);
        window.setTimeout(() => active && setFillStage("filled"), 650);
      } catch (error) {
        message.error(error instanceof Error ? error.message : "读取申请表单失败");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, [caseId, message]);

  async function updateField(field: ApplicationField, value: unknown) {
    if (!detail) return;
    setWorking(true);
    try {
      const updated = await updateApplicationDraftField(detail.id, field.key, value, field.revision);
      setDetail((current) => current ? { ...current, fields: current.fields.map((item) => item.key === field.key ? { ...item, ...updated } : item) } : current);
      message.success(`${field.label}已保存，等待同步。`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "字段保存失败");
    } finally { setWorking(false); }
  }

  async function uploadMaterial(materialKey: string, file: File) {
    if (!detail) return;
    setWorking(true);
    try {
      await uploadApplicationMaterial(detail.id, materialKey, file);
      setDetail((current) => current ? { ...current, materials: current.materials.map((item) => item.key === materialKey ? { ...item, status: "uploaded" } : item) } : current);
      message.success("材料已保存到申请草稿。");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "材料上传失败");
    } finally { setWorking(false); }
  }

  async function continueToOfficialForm() {
    if (!detail) return;
    setWorking(true);
    try {
      if (!detail.browser) {
        const browser = await connectApplicationBrowser(detail.id);
        setDetail((current) => current ? { ...current, browser } : current);
        message.success("Agent 已打开已登记的官方表单入口。");
        return;
      }
      let result = await syncApplicationDraft(detail.id, false);
      if (result.requires_approval) {
        const sensitive = result.sensitive_fields?.join("、") || "敏感字段";
        Modal.confirm({
          title: "确认同步敏感字段", content: `将同步：${sensitive}。不会自动提交申请。`, okText: "确认同步", cancelText: "取消",
          onOk: async () => {
            result = await syncApplicationDraft(detail.id, true);
            setDetail((current) => current ? { ...current, status: "REVIEW", current_step: "review", fields: current.fields.map((field) => field.value != null ? { ...field, sync_state: "synced" } : field), next_action: { code: "WAITING_USER", message: result.message } } : current);
            message.success("已同步；请在官方页面完成验证码、承诺和提交。");
          },
        });
      } else {
        setDetail((current) => current ? { ...current, status: "REVIEW", current_step: "review", next_action: { code: "WAITING_USER", message: result.message } } : current);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "无法继续官方表单流程");
    } finally { setWorking(false); }
  }

  async function submitDemoApplication() {
    if (!detail) return;
    Modal.confirm({
      title: "确认提交申请？",
      content: "这只会记录演示流程中的提交动作，不会向真实官方系统提交。",
      okText: "确认提交", cancelText: "取消",
      onOk: async () => {
        setWorking(true);
        try {
          const result = await submitApplication(detail.id);
          setDetail((current) => current ? { ...current, status: result.status, current_step: result.current_step, next_action: { code: "SUBMITTED", message: result.message } } : current);
          message.success(result.message);
        } catch (error) { message.error(error instanceof Error ? error.message : "提交申请失败"); }
        finally { setWorking(false); }
      },
    });
  }

  const currentStep = detail ? Math.max(0, detail.definition.steps.findIndex((step) => step.code === detail.current_step)) : 0;
  return <Modal open={open} onCancel={onClose} footer={null} width={900} destroyOnClose title={<Space><span>{title}</span><Tag color="cyan">Agent 已发起</Tag></Space>}>
    {loading || !detail ? <div className="application-dialog-loading"><Spin tip="Agent 正在读取流程并带入可用信息…" /></div> : <div className="application-dialog">
      <Alert type={fillStage === "reading" ? "info" : "success"} showIcon message={fillStage === "reading" ? "Agent 正在带入个人档案信息…" : "已完成可用信息带入；其余字段请您核对或补充。"} />
      <Steps size="small" current={currentStep} items={detail.definition.steps.map((step) => ({ title: step.name }))} />
      <div className="application-dialog-grid">
        <section>
          <Title level={4}>申请表单</Title>
          <Form layout="vertical">
            {detail.fields.map((field) => <DialogField key={field.key} field={field} working={working} onSave={updateField} />)}
          </Form>
        </section>
        <aside className="application-dialog-side">
          <Timeline items={detail.fields.filter((field) => field.value != null).map((field) => ({ color: "green", children: <span>已带入 {field.label}<Tag>{SOURCE_LABELS[field.source || ""] || "已填写"}</Tag></span> }))} />
          <section>
            <Text strong>材料</Text>
            {detail.materials.map((material) => <div className="application-material" key={material.key}><Text>{material.label}</Text>{material.status === "uploaded" ? <Tag color="success">已上传</Tag> : <Upload showUploadList={false} beforeUpload={(file) => { void uploadMaterial(material.key, file); return false; }}><Button size="small" loading={working}>上传</Button></Upload>}</div>)}
          </section>
          <Descriptions size="small" column={1} title="Agent 流程">
            <Descriptions.Item label="官方入口">{detail.browser ? "已打开" : "等待打开"}</Descriptions.Item>
            <Descriptions.Item label="下一步">{detail.next_action?.message}</Descriptions.Item>
          </Descriptions>
          <Space direction="vertical" style={{ width: "100%" }}>
            <Button block type="primary" icon={detail.browser ? <SyncOutlined /> : <GlobalOutlined />} loading={working} disabled={detail.next_action?.code === "FILL_FIELDS" || detail.next_action?.code === "UPLOAD_MATERIALS"} onClick={() => void continueToOfficialForm()}>{detail.browser ? "同步到官方表单" : "Agent 打开官方表单"}</Button>
            <Button block type="primary" danger icon={<CheckCircleOutlined />} loading={working} onClick={() => void submitDemoApplication()}>提交申请（演示）</Button>
          </Space>
          <Alert type="warning" showIcon icon={<SafetyCertificateOutlined />} message="最终提交由您操作" description="验证码、人脸、声明和提交不会由 Agent 自动执行。" />
        </aside>
      </div>
    </div>}
  </Modal>;
}

function DialogField({ field, working, onSave }: { field: ApplicationField; working: boolean; onSave: (field: ApplicationField, value: unknown) => Promise<void> }) {
  const [value, setValue] = useState<unknown>(field.value ?? undefined);
  useEffect(() => { setValue(field.value ?? undefined); }, [field.value]);
  const input = field.type === "select" ? <Select value={value as boolean | undefined} options={field.options} disabled={!field.editable || working} onChange={setValue} /> : <Input value={value as string | undefined} type={field.type === "date" ? "date" : "text"} disabled={!field.editable || working} onChange={(event) => setValue(event.target.value)} />;
  return <Form.Item label={<Space><span>{field.label}{field.required ? " *" : ""}</span><Tag>{SOURCE_LABELS[field.source || ""] || "待填写"}</Tag><Tag color={field.sync_state === "synced" ? "success" : "default"}>{field.sync_state === "synced" ? "已同步" : "待同步"}</Tag></Space>}><div className="application-field-row">{input}{field.editable && <Button disabled={working || value === field.value} onClick={() => void onSave(field, value)}>保存</Button>}</div></Form.Item>;
}
