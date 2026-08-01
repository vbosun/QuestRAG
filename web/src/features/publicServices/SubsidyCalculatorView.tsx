import { App, Button, Card, Descriptions, Empty, Form, Input, List, Space, Tag, Typography } from "antd";
import { useMemo, useState } from "react";

import { calculateSubsidy, matchSubsidies } from "../../api";
import type { RequiredInput, SubsidyCalculationResult, SubsidyMatchResult } from "../../types";

const { Text, Title, Paragraph } = Typography;

export function SubsidyCalculatorView() {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [description, setDescription] = useState("我毕业两年没工作，自己交社保能领补贴吗？");
  const [matches, setMatches] = useState<SubsidyMatchResult[]>([]);
  const [active, setActive] = useState<SubsidyMatchResult | null>(null);
  const [result, setResult] = useState<SubsidyCalculationResult | null>(null);
  const [loading, setLoading] = useState(false);

  const missingInputs = useMemo<RequiredInput[]>(() => active?.missing_inputs || result?.missing_inputs || [], [active, result]);

  async function handleMatch() {
    if (!description.trim()) {
      message.warning("请先输入个人情况");
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const data = await matchSubsidies({ user_description: description, top_k: 5 });
      setMatches(data);
      setActive(data[0] || null);
      form.resetFields();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "补贴匹配失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleCalculate(policyId?: string) {
    const target = policyId || active?.policy_id;
    if (!target) return;
    setLoading(true);
    try {
      const values = form.getFieldsValue();
      const data = await calculateSubsidy({ policy_id: target, user_inputs: normalizeInputs(values) });
      setResult(data);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "补贴测算失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="view-shell public-service-view">
      <div className="panel-header">
        <div>
          <Text type="secondary">政务工具</Text>
          <Title level={2}>补贴测算</Title>
          <Text type="secondary">规则引擎测算金额，政策依据仍以知识库原文为准</Text>
        </div>
      </div>
      <div className="public-service-body subsidy-layout">
        <Card size="small" title="输入个人情况">
          <Input.TextArea
            value={description}
            rows={5}
            placeholder="例如：我是2025年毕业的，已经办理灵活就业登记，自己交了8个月社保"
            onChange={(event) => setDescription(event.target.value)}
          />
          <Button className="subsidy-action" loading={loading} type="primary" onClick={handleMatch}>
            开始匹配
          </Button>
        </Card>

        <Card size="small" title="候选补贴">
          {matches.length ? (
            <List
              dataSource={matches}
              renderItem={(item) => (
                <List.Item
                  className={active?.policy_id === item.policy_id ? "subsidy-match active" : "subsidy-match"}
                  onClick={() => {
                    setActive(item);
                    setResult(null);
                    form.resetFields();
                  }}
                  actions={[<Button size="small" type="link" onClick={() => void handleCalculate(item.policy_id)}>测算</Button>]}
                >
                  <List.Item.Meta
                    title={<Space><span>{item.policy_name}</span><Tag color={statusColor(item.match_status)}>{statusLabel(item.match_status)}</Tag></Space>}
                    description={`匹配分 ${item.match_score.toFixed(0)}，缺失 ${item.missing_inputs.length} 项`}
                  />
                </List.Item>
              )}
            />
          ) : <Empty description="输入情况后查看候选补贴" />}
        </Card>

        <Card size="small" title="补充信息与测算详情" className="subsidy-detail">
          {active && missingInputs.length > 0 && (
            <Form form={form} layout="vertical">
              {missingInputs.map((item) => (
                <Form.Item key={item.field} label={item.label} name={item.field}>
                  <Input placeholder={placeholderFor(item.field)} />
                </Form.Item>
              ))}
              <Button loading={loading} type="primary" onClick={() => void handleCalculate()}>
                补充后测算
              </Button>
            </Form>
          )}

          {result ? (
            <div className="subsidy-result">
              <Descriptions column={2} size="small">
                <Descriptions.Item label="测算结论"><Tag color={statusColor(result.status)}>{statusLabel(result.status)}</Tag></Descriptions.Item>
                <Descriptions.Item label="预计金额">{result.estimated_amount ? `${result.estimated_amount.toFixed(2)} ${result.amount_unit}` : "-"}</Descriptions.Item>
                <Descriptions.Item label="政策依据">{result.source_doc_id || "-"}</Descriptions.Item>
              </Descriptions>
              <Section title="计算过程" items={result.calculation_steps} />
              <Section title="办理材料" items={result.materials} />
              <Section title="办理流程" items={result.process_steps} />
              <Paragraph type="secondary">{result.disclaimer}</Paragraph>
            </div>
          ) : active ? (
            <Text type="secondary">选择候选补贴后，可直接测算；如缺少关键信息，先补充字段。</Text>
          ) : (
            <Empty description="暂无测算详情" />
          )}
        </Card>
      </div>
    </div>
  );
}

function Section({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="subsidy-section">
      <Text strong>{title}</Text>
      <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function normalizeInputs(values: Record<string, unknown>) {
  const normalized: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (value === undefined || value === "") continue;
    if (["is_college_graduate", "first_business"].includes(key)) {
      normalized[key] = ["true", "是", "1", "yes"].includes(String(value).toLowerCase());
    } else if (["graduation_year", "business_months"].includes(key)) {
      normalized[key] = Number(value);
    } else if (key === "person_tags") {
      normalized[key] = String(value).split(/[,，\s]+/).filter(Boolean);
    } else {
      normalized[key] = value;
    }
  }
  return normalized;
}

function placeholderFor(field: string) {
  const map: Record<string, string> = {
    is_college_graduate: "请输入 是 / 否",
    graduation_year: "例如 2025",
    employment_status: "例如 flexible_employment",
    person_tags: "例如 college_graduate_within_2_years",
    business_status: "例如 active",
    business_months: "例如 12",
    first_business: "请输入 是 / 否",
  };
  return map[field] || "请补充该字段";
}

function statusLabel(value: string) {
  return { eligible: "可申请", possible: "可能符合", missing_info: "需补充信息", not_eligible: "暂不符合" }[value] || value;
}

function statusColor(value: string) {
  return { eligible: "success", possible: "warning", missing_info: "warning", not_eligible: "error" }[value] || "default";
}
