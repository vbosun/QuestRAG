import { CheckCircleOutlined, GlobalOutlined, SafetyCertificateOutlined, SyncOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Descriptions, Divider, Form, Input, Modal, Select, Space, Spin, Steps, Tag, Typography, Upload } from "antd";
import { useEffect, useState } from "react";
import { connectApplicationBrowser, createApplicationCase, getApplicationCase, listApplicationCases, listApplicationDefinitions, syncApplicationDraft, updateApplicationDraftField, uploadApplicationMaterial } from "../../api";
import type { ApplicationDefinitionSummary, ApplicationDetail, ApplicationField } from "./types";

const { Paragraph, Text, Title } = Typography;

const SOURCE_LABELS: Record<string, string> = {
  user_manual: "用户填写",
  agent_suggested: "Agent 建议",
  profile_prefill: "个人档案带入",
  official_readonly: "官方只读",
  official_observed: "官方页面读取",
};

export function ApplicationWorkspace() {
  const { message } = App.useApp();
  const [definitions, setDefinitions] = useState<ApplicationDefinitionSummary[]>([]);
  const [cases, setCases] = useState<Array<Pick<ApplicationDetail, "id" | "business_code" | "status" | "current_step">>>([]);
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);

  async function loadDefinitions() {
    setLoading(true);
    try {
      const [nextDefinitions, nextCases] = await Promise.all([listApplicationDefinitions(), listApplicationCases()]);
      setDefinitions(nextDefinitions);
      setCases(nextCases);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "加载办事事项失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadDefinitions(); }, []);

  async function startApplication(businessCode: string) {
    setWorking(true);
    try {
      setDetail(await createApplicationCase(businessCode));
      setCases(await listApplicationCases());
      message.success("已为您创建申请草稿，您可以先填写或修改表单。");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "创建申请失败");
    } finally {
      setWorking(false);
    }
  }

  async function resumeApplication(caseId: string) {
    setWorking(true);
    try {
      setDetail(await getApplicationCase(caseId));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取申请草稿失败");
    } finally {
      setWorking(false);
    }
  }

  async function updateField(field: ApplicationField, value: unknown) {
    if (!detail) return;
    setWorking(true);
    try {
      const updated = await updateApplicationDraftField(detail.id, field.key, value, field.revision);
      setDetail((current) => current ? {
        ...current,
        fields: current.fields.map((item) => item.key === field.key ? { ...item, ...updated } : item),
      } : current);
      message.success("已保存到申请草稿，等待同步到官方表单。");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "字段保存失败");
    } finally {
      setWorking(false);
    }
  }

  async function connectBrowser() {
    if (!detail) return;
    setWorking(true);
    try {
      const browser = await connectApplicationBrowser(detail.id);
      setDetail((current) => current ? { ...current, browser, next_action: { code: "SYNC_DRAFT", message: "已连接演示浏览器，请确认同步表单。" } } : current);
      message.success("Agent 已连接独立业务系统，页面保持在当前界面。");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "浏览器连接失败");
    } finally {
      setWorking(false);
    }
  }

  async function syncDraft() {
    if (!detail) return;
    setWorking(true);
    try {
      let result = await syncApplicationDraft(detail.id, false);
      if (result.requires_approval) {
        const sensitive = result.sensitive_fields?.join("、") || "敏感字段";
        const approved = await new Promise<boolean>((resolve) => {
          Modal.confirm({
            title: "确认同步敏感字段",
            content: `本次会同步：${sensitive}。仅同步到当前已登记的演示官方表单，不会自动提交申请。`,
            okText: "确认同步", cancelText: "取消", onOk: () => resolve(true), onCancel: () => resolve(false),
          });
        });
        if (!approved) return;
        result = await syncApplicationDraft(detail.id, true);
      }
      setDetail((current) => current ? {
        ...current,
        status: "REVIEW", current_step: "review",
        fields: current.fields.map((field) => field.value !== null && field.value !== undefined ? { ...field, sync_state: "synced" } : field),
        next_action: { code: "WAITING_USER", message: result.message },
      } : current);
      message.success("已同步。验证码、承诺和提交仍需由您在官方页面完成。");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "同步失败");
    } finally {
      setWorking(false);
    }
  }

  async function uploadMaterial(materialKey: string, file: File) {
    if (!detail) return;
    setWorking(true);
    try {
      await uploadApplicationMaterial(detail.id, materialKey, file);
      setDetail((current) => current ? {
        ...current,
        materials: current.materials.map((material) => material.key === materialKey ? { ...material, status: "uploaded" } : material),
      } : current);
      message.success("材料已保存到申请草稿，等待同步到官方页面。");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "材料上传失败");
    } finally {
      setWorking(false);
    }
  }

  if (loading) return <div className="application-loading"><Spin /></div>;

  if (!detail) {
    return <section className="view-shell application-view">
      <header className="application-hero">
        <Tag color="cyan">办事 Agent 试点</Tag>
        <Title level={2}>把办事流程交给 Agent，把表单控制权留给您</Title>
        <Paragraph>选择一项服务后，Agent 会判断流程并打开已登记的官方入口；您只需在这里编辑必要表单。</Paragraph>
      </header>
      <div className="application-definition-grid">
        {definitions.map((definition) => (
          <Card key={definition.business_code} className="application-definition-card">
            <Tag>{definition.region}</Tag>
            <Title level={4}>{definition.name}</Title>
            <Text type="secondary">{definition.official_service_name}</Text>
            <Divider />
            <Button type="primary" block loading={working} onClick={() => void startApplication(definition.business_code)}>开始办理</Button>
          </Card>
        ))}
      </div>
      {cases.length > 0 && <Card title="继续未完成的申请" className="application-resume-card">
        <Space wrap>{cases.map((item) => <Button key={item.id} loading={working} onClick={() => void resumeApplication(item.id)}>{item.business_code} · {item.current_step}</Button>)}</Space>
      </Card>}
    </section>;
  }

  const currentStep = Math.max(0, detail.definition.steps.findIndex((step) => step.code === detail.current_step));
  return <section className="view-shell application-view">
    <header className="application-header">
      <div>
        <Tag color="cyan">{detail.definition.region}</Tag>
        <Title level={2}>{detail.definition.name}</Title>
        <Text type="secondary">{detail.definition.official_service_name} · 当前仅接入受控演示适配器</Text>
      </div>
      <Tag color={detail.browser?.status === "connected" ? "success" : "default"} icon={<GlobalOutlined />}>
        {detail.browser?.status === "connected" ? "已连接本机浏览器" : "浏览器尚未连接"}
      </Tag>
    </header>
    <Steps current={currentStep} items={detail.definition.steps.map((step) => ({ title: step.name }))} />
    <Alert className="application-next-action" type="info" showIcon message={detail.next_action?.message || "请完成当前步骤"} />
    <div className="application-workspace-grid">
      <Card className="application-form-card" title="当前申请表单" extra={<Tag icon={<SyncOutlined />}>{detail.fields.filter((field) => field.sync_state === "synced").length}/{detail.fields.length} 已同步</Tag>}>
        <Form layout="vertical">
          {detail.fields.map((field) => <ApplicationFieldEditor key={field.key} field={field} working={working} onSave={updateField} />)}
        </Form>
      </Card>
      <aside className="application-sidebar">
        <Card title="材料与校验" size="small">
          {detail.materials.map((material) => <div className="application-material" key={material.key}>
            <Text>{material.label}</Text>
            {material.status === "uploaded" ? <Tag color="success">已上传</Tag> : <Upload showUploadList={false} beforeUpload={(file) => { void uploadMaterial(material.key, file); return false; }}><Button size="small" loading={working}>上传</Button></Upload>}
          </div>)}
        </Card>
        <Card title="Agent 执行状态" size="small">
          <Descriptions column={1} size="small">
            <Descriptions.Item label="官方入口">{detail.browser ? "已由 Agent 打开" : "等待资料齐全"}</Descriptions.Item>
            <Descriptions.Item label="页面范围">仅已登记的表单路径</Descriptions.Item>
            <Descriptions.Item label="最终提交">必须由用户完成</Descriptions.Item>
          </Descriptions>
          {!detail.browser ? <Button block type="primary" icon={<GlobalOutlined />} loading={working} disabled={detail.next_action?.code === "FILL_FIELDS" || detail.next_action?.code === "UPLOAD_MATERIALS"} onClick={() => void connectBrowser()}>由 Agent 打开官方表单</Button> : <Button block type="primary" icon={<CheckCircleOutlined />} loading={working} disabled={detail.next_action?.code === "FILL_FIELDS" || detail.next_action?.code === "UPLOAD_MATERIALS"} onClick={() => void syncDraft()}>确认同步到官方表单</Button>}
        </Card>
        <Alert type="warning" showIcon icon={<SafetyCertificateOutlined />} message="安全边界" description="验证码、人脸、声明承诺和最终提交不会由 Agent 自动执行。" />
      </aside>
    </div>
  </section>;
}

function ApplicationFieldEditor({ field, working, onSave }: { field: ApplicationField; working: boolean; onSave: (field: ApplicationField, value: unknown) => Promise<void> }) {
  const [value, setValue] = useState<unknown>(field.value ?? undefined);
  useEffect(() => { setValue(field.value ?? undefined); }, [field.value]);
  const input = field.type === "select" ? <Select value={value as boolean | undefined} options={field.options} disabled={!field.editable || working} onChange={setValue} /> : <Input value={value as string | undefined} type={field.type === "date" ? "date" : "text"} disabled={!field.editable || working} onChange={(event) => setValue(event.target.value)} />;
  return <Form.Item label={<Space><span>{field.label}{field.required ? " *" : ""}</span><Tag>{SOURCE_LABELS[field.source || ""] || "待填写"}</Tag><Tag color={field.sync_state === "synced" ? "success" : "default"}>{field.sync_state === "synced" ? "已同步" : "待同步"}</Tag></Space>}>
    <div className="application-field-row">{input}{field.editable && <Button disabled={working || value === field.value} onClick={() => void onSave(field, value)}>保存</Button>}</div>
  </Form.Item>;
}
