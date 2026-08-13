import { CheckOutlined, RollbackOutlined, SendOutlined } from "@ant-design/icons";
import { App, Button, Card, Empty, List, Select, Space, Steps, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { actWorkflow, listWorkflowDefinitions, listWorkflowInstances, startWorkflow } from "../../api";

const { Text, Title } = Typography;

type Definition = { business_code: string; name: string; version: string; nodes: Array<{ code: string; name: string; kind: string; role?: string | null }> };
type Instance = any;

export function WorkflowCenter() {
  const { message } = App.useApp();
  const [definitions, setDefinitions] = useState<Definition[]>([]);
  const [instances, setInstances] = useState<Instance[]>([]);
  const [selected, setSelected] = useState<string>();
  const [working, setWorking] = useState(false);

  async function refresh() {
    try {
      const [nextDefinitions, nextInstances] = await Promise.all([listWorkflowDefinitions(), listWorkflowInstances()]);
      setDefinitions(nextDefinitions); setInstances(nextInstances);
    } catch (error) { message.error(error instanceof Error ? error.message : "加载流程中心失败"); }
  }
  useEffect(() => { void refresh(); }, []);

  async function start() {
    if (!selected) return;
    setWorking(true);
    try { await startWorkflow(selected); await refresh(); message.success("已创建流程申请，可开始提交审批"); }
    catch (error) { message.error(error instanceof Error ? error.message : "发起流程失败"); }
    finally { setWorking(false); }
  }

  async function action(caseId: string, name: string) {
    setWorking(true);
    try { await actWorkflow(caseId, name); await refresh(); message.success("流程状态已更新"); }
    catch (error) { message.error(error instanceof Error ? error.message : "流程操作失败"); }
    finally { setWorking(false); }
  }

  return <section className="view-shell application-view">
    <header className="application-hero"><Tag color="purple">Agent 审批测试中心</Tag><Title level={2}>业务流程办理中心</Title><Text type="secondary">配置业务流程、发起申请，模拟多级审批、退回和再次提交。</Text></header>
    <Card title="流程定义" extra={<Button onClick={() => void refresh()}>刷新</Button>}>
      <Space wrap><Select style={{ minWidth: 280 }} placeholder="选择业务流程" value={selected} onChange={setSelected} options={definitions.map((item) => ({ value: item.business_code, label: `${item.name} · v${item.version}` }))} /><Button type="primary" loading={working} disabled={!selected} onClick={() => void start()}>发起测试申请</Button></Space>
      {selected && <Steps className="workflow-steps" size="small" items={(definitions.find((item) => item.business_code === selected)?.nodes || []).map((node) => ({ title: node.name, description: node.role || "系统" }))} />}
    </Card>
    <Card title="流程实例" style={{ marginTop: 16 }}>
      {!instances.length ? <Empty description="暂无测试申请" /> : <List dataSource={instances} renderItem={(item) => <List.Item actions={item.pending_task ? [item.pending_task.node_code === "APPLICANT" ? <Button key="submit" icon={<SendOutlined />} loading={working} onClick={() => void action(item.id, "submit")}>提交审批</Button> : <><Button key="approve" type="primary" icon={<CheckOutlined />} loading={working} onClick={() => void action(item.id, "approve")}>同意</Button><Button key="return" icon={<RollbackOutlined />} loading={working} onClick={() => void action(item.id, "return")}>退回</Button></>] : []}><List.Item.Meta title={<Space>{item.definition?.name}<Tag>{item.status}</Tag></Space>} description={<><Text type="secondary">当前节点：{item.current_step}</Text><Steps size="small" current={Math.max(0, item.workflow.nodes.findIndex((node: any) => node.code === item.current_step))} items={item.workflow.nodes.map((node: any) => ({ title: node.name }))} /></>} /></List.Item>} />}
    </Card>
  </section>;
}
