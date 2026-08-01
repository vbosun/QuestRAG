import { ReloadOutlined, SaveOutlined, SyncOutlined } from "@ant-design/icons";
import { App, Breadcrumb, Button, Descriptions, InputNumber, Select, Space, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { getRetrievalConfig, listEvaluations, syncRetrievalConfig, updateRetrievalConfig } from "../../api";
import type { EvaluationRun, RetrievalOptions } from "../../types";
import { formatDate } from "../../utils";

const { Title, Text } = Typography;

export function RetrievalConfigView() {
  const { message } = App.useApp();
  const [config, setConfig] = useState<RetrievalOptions>({ top_k: 5, recall_k: 15, mode: "hybrid", rrf_k: 60 });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [evaluations, setEvaluations] = useState<EvaluationRun[]>([]);
  const [syncRunId, setSyncRunId] = useState<string | undefined>();

  useEffect(() => {
    void loadConfig();
    void loadEvaluations();
  }, []);

  async function loadConfig() {
    setLoading(true);
    try {
      const cfg = await getRetrievalConfig();
      setConfig(cfg);
    } catch (err) {
      message.error(err instanceof Error ? err.message : "读取检索配置失败");
    } finally {
      setLoading(false);
    }
  }

  async function loadEvaluations() {
    try {
      setEvaluations(await listEvaluations());
    } catch {
      // non-critical
    }
  }

  async function handleSave() {
    setSaving(true);
    try {
      await updateRetrievalConfig(config);
      message.success("检索参数已保存，正式检索即时生效");
    } catch (err) {
      message.error(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleSync() {
    if (!syncRunId) {
      message.warning("请选择一条评测记录");
      return;
    }
    setSyncing(true);
    try {
      await syncRetrievalConfig(syncRunId);
      message.success("已从评测记录同步检索参数");
      await loadConfig();
    } catch (err) {
      message.error(err instanceof Error ? err.message : "同步失败");
    } finally {
      setSyncing(false);
    }
  }

  const modeLabel: Record<string, string> = { hybrid: "混合检索", vector: "向量检索", keyword: "关键词检索" };

  return (
    <section className="view-shell">
      <header className="panel-header">
        <div>
          <div className="page-nav-row">
            <Breadcrumb className="page-breadcrumb" items={[{ title: "检索配置" }]} />
          </div>
          <div className="page-title-block">
            <Title level={3}>检索配置</Title>
            <Text type="secondary" className="page-subtitle">调整正式环境的检索参数，保存后即时生效，无需重启。</Text>
          </div>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadConfig} loading={loading}>
            刷新
          </Button>
        </Space>
      </header>

      <main className="eval-detail-page">
        <section className="eval-detail-card">
          <div className="ingest-card-header">
            <Title level={4}>当前参数</Title>
            <Button icon={<SaveOutlined />} loading={saving} onClick={handleSave} type="primary">
              保存
            </Button>
          </div>

          <div className="eval-option-grid">
            <label>
              <Text strong>Top K（最终返回数）</Text>
              <InputNumber
                min={1}
                max={20}
                value={config.top_k}
                onChange={(value) => setConfig({ ...config, top_k: Number(value || 5) })}
              />
            </label>
            <label>
              <Text strong>每路召回数 (recall_k)</Text>
              <InputNumber
                min={1}
                max={50}
                value={config.recall_k}
                onChange={(value) => setConfig({ ...config, recall_k: Number(value || 15) })}
              />
            </label>
            <label>
              <Text strong>检索模式</Text>
              <Select
                value={config.mode}
                options={[
                  { value: "hybrid", label: "混合检索" },
                  { value: "vector", label: "向量检索" },
                  { value: "keyword", label: "关键词检索" },
                ]}
                onChange={(value) => setConfig({ ...config, mode: value })}
              />
            </label>
            <label>
              <Text strong>RRF 平滑参数 (k)</Text>
              <InputNumber
                min={1}
                max={120}
                value={config.rrf_k}
                onChange={(value) => setConfig({ ...config, rrf_k: Number(value || 60) })}
              />
            </label>
          </div>

          <Descriptions bordered column={2} size="small" style={{ marginTop: 24 }}>
            <Descriptions.Item label="Top K">{config.top_k}</Descriptions.Item>
            <Descriptions.Item label="模式"><Tag>{modeLabel[config.mode] || config.mode}</Tag></Descriptions.Item>
            <Descriptions.Item label="召回数">{config.recall_k}</Descriptions.Item>
            <Descriptions.Item label="RRF k">{config.rrf_k}</Descriptions.Item>
          </Descriptions>
        </section>

        <section className="eval-detail-card">
          <Title level={4}>从评测记录同步</Title>
          <Text type="secondary">选择一条已完成评测的记录，将其检索参数一键应用到正式环境。</Text>
          <Space style={{ marginTop: 16 }}>
            <Select
              allowClear
              onChange={(value) => setSyncRunId(value)}
              options={evaluations
                .filter((r) => r.status === "completed")
                .map((r) => ({
                  value: r.id,
                  label: `${r.name}（${formatDate(r.created_at)}）`,
                }))}
              placeholder="选择评测记录"
              style={{ minWidth: 360 }}
              value={syncRunId}
            />
            <Button icon={<SyncOutlined />} loading={syncing} onClick={handleSync}>
              同步参数
            </Button>
          </Space>
        </section>
      </main>
    </section>
  );
}
