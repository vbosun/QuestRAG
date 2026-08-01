import { App, Button, Card, Col, Descriptions, Row, Statistic, Table, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getSocialSecuritySummary, listSocialSecurityPayments } from "../../api";
import type { SocialSecurityPaymentRecord, SocialSecuritySummary } from "../../types";

const { Text, Title } = Typography;

export function SocialSecurityView() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [summary, setSummary] = useState<SocialSecuritySummary | null>(null);
  const [payments, setPayments] = useState<SocialSecurityPaymentRecord[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void refresh();
  }, []);

  async function refresh() {
    setLoading(true);
    try {
      const [nextSummary, nextPayments] = await Promise.all([
        getSocialSecuritySummary(),
        listSocialSecurityPayments({ limit: 24 }),
      ]);
      setSummary(nextSummary);
      setPayments(nextPayments);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取社保数据失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="view-shell public-service-view">
      <div className="panel-header">
        <div>
          <Text type="secondary">政务工具</Text>
          <Title level={2}>社保查询</Title>
          <Text type="secondary">仅展示当前登录用户本人的模拟社保数据</Text>
        </div>
        <Button type="primary" onClick={() => navigate("/app/public-services/subsidy-calculator")}>
          用社保数据测算补贴
        </Button>
      </div>
      <div className="public-service-body">
        <Row gutter={[12, 12]}>
          <Col xs={24} md={6}>
            <Card size="small"><Statistic title="参保状态" value={statusLabel(summary?.insured_status)} /></Card>
          </Col>
          <Col xs={24} md={6}>
            <Card size="small"><Statistic title="当前缴费基数" value={summary?.current_base || 0} suffix="元" precision={2} /></Card>
          </Col>
          <Col xs={24} md={6}>
            <Card size="small"><Statistic title="累计缴费月数" value={summary?.total_payment_months || 0} suffix="个月" /></Card>
          </Col>
          <Col xs={24} md={6}>
            <Card size="small"><Statistic title="养老账户余额" value={summary?.pension_account_balance || 0} suffix="元" precision={2} /></Card>
          </Col>
        </Row>

        <Card size="small" title="参保概要">
          <Descriptions column={3} size="small">
            <Descriptions.Item label="当前参保单位">{summary?.insured_unit || "未登记"}</Descriptions.Item>
            <Descriptions.Item label="首次参保日期">{summary?.first_insured_date || "-"}</Descriptions.Item>
            <Descriptions.Item label="医保账户余额">{(summary?.medical_account_balance || 0).toFixed(2)} 元</Descriptions.Item>
          </Descriptions>
        </Card>

        <Card size="small" title="缴费记录">
          <Table
            loading={loading}
            rowKey={(row) => `${row.payment_month}-${row.insurance_type}`}
            dataSource={payments}
            pagination={{ pageSize: 10 }}
            columns={[
              { title: "缴费月份", dataIndex: "payment_month", width: 110 },
              { title: "险种", dataIndex: "insurance_type", width: 100, render: (value) => insuranceLabel(value) },
              { title: "缴费基数", dataIndex: "payment_base", render: money },
              { title: "个人缴费", dataIndex: "personal_amount", render: money },
              { title: "单位缴费", dataIndex: "company_amount", render: money },
              { title: "合计", dataIndex: "total_amount", render: money },
              { title: "状态", dataIndex: "paid_status", render: (value) => <Tag color="success">{value === "PAID" ? "已缴" : value}</Tag> },
            ]}
          />
        </Card>
      </div>
    </div>
  );
}

function money(value: number) {
  return `${Number(value || 0).toFixed(2)} 元`;
}

function statusLabel(value?: string) {
  return { ACTIVE: "正常参保", PAUSED: "暂停参保", TERMINATED: "终止参保", NONE: "无记录" }[value || ""] || "-";
}

function insuranceLabel(value: string) {
  return { PENSION: "养老", MEDICAL: "医疗", UNEMPLOYMENT: "失业", WORK_INJURY: "工伤", MATERNITY: "生育" }[value] || value;
}

