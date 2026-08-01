import { ArrowLeftOutlined, CheckCircleOutlined, DeleteOutlined, PlusOutlined, ReloadOutlined, UploadOutlined } from "@ant-design/icons";
import { App, Breadcrumb, Button, Checkbox, Descriptions, Empty, Input, InputNumber, List, Modal, Popconfirm, Select, Space, Steps, Table, Tag, Typography, Upload } from "antd";
import type { UploadRequestOption } from "rc-upload/lib/interface";
import { useEffect, useState } from "react";
import {
  createEvaluationDataset,
  deleteEvaluationDataset,
  deleteEvaluationDocument,
  exportEvaluationDataset,
  getEvaluation,
  getEvaluationDataset,
  getEvaluationDocument,
  importEvaluationDataset,
  listEvaluationDocumentRunChunks,
  listEvaluationDocumentRuns,
  listEvaluationDatasets,
  listEvaluationDocuments,
  runEvaluation,
  updateEvaluationDataset,
  uploadEvaluationDocuments
} from "../../api";
import type { CleanOptions, DocumentChunk, DocumentInfo, EvaluationDataset, EvaluationDatasetItem, EvaluationDocument, EvaluationDocumentRun, EvaluationItem, EvaluationRun, RetrievalOptions, SplitOptions } from "../../types";
import { evalStatusLabel, formatDate, formatRate, summarizeRetrieved } from "../../utils";

const { Text, Title } = Typography;
const JOB_SOURCE_ID = "jobs::__es_index__";
const JOB_SOURCE_OPTION = { value: JOB_SOURCE_ID, label: "岗位库（ES）" };

export function EvaluationView({
  documents,
  evaluationError,
  evaluations,
  initialMode,
  resetKey,
  loadingEvaluations,
  onDeleteEvaluation,
  onRefreshDocuments,
  onRefreshEvaluations
}: {
  documents: DocumentInfo[];
  evaluationError: string;
  evaluations: EvaluationRun[];
  initialMode: "list" | "documents" | "datasets";
  resetKey?: number;
  loadingEvaluations: boolean;
  onDeleteEvaluation: (run: EvaluationRun) => Promise<void>;
  onRefreshDocuments: () => Promise<void>;
  onRefreshEvaluations: () => Promise<void>;
}) {
  const { message } = App.useApp();
  const [mode, setMode] = useState<"list" | "create" | "detail" | "documents" | "documentDetail" | "documentRunChunks" | "datasets" | "datasetEdit">(initialMode);
  const [step, setStep] = useState(0);

  useEffect(() => {
    setMode(initialMode);
    setStep(0);
    setActiveRun(null);
    setActiveRetrievedItem(null);
    setActiveEvalDocument(null);
    setActiveDataset(null);
  }, [initialMode, resetKey]);
  const [activeRun, setActiveRun] = useState<EvaluationRun | null>(null);
  const [activeRetrievedItem, setActiveRetrievedItem] = useState<EvaluationItem | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [running, setRunning] = useState(false);
  const [name, setName] = useState(`检索评测 ${new Date().toLocaleString("zh-CN", { hour12: false })}`);
  const [datasetId, setDatasetId] = useState("");
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  const [evalDocuments, setEvalDocuments] = useState<EvaluationDocument[]>([]);
  const [evalDatasets, setEvalDatasets] = useState<EvaluationDataset[]>([]);
  const [activeEvalDocument, setActiveEvalDocument] = useState<EvaluationDocument | null>(null);
  const [activeEvalDocumentRuns, setActiveEvalDocumentRuns] = useState<EvaluationDocumentRun[]>([]);
  const [activeEvalDocumentRun, setActiveEvalDocumentRun] = useState<EvaluationDocumentRun | null>(null);
  const [activeEvalRunChunks, setActiveEvalRunChunks] = useState<DocumentChunk[]>([]);
  const [loadingEvalDocumentRuns, setLoadingEvalDocumentRuns] = useState(false);
  const [loadingEvalRunChunks, setLoadingEvalRunChunks] = useState(false);
  const [activeDataset, setActiveDataset] = useState<EvaluationDataset | null>(null);
  const [loadingEvalAssets, setLoadingEvalAssets] = useState(false);
  const [uploadingEvalDocuments, setUploadingEvalDocuments] = useState(false);
  const [importingDataset, setImportingDataset] = useState(false);
  const [editingDatasetItemIndex, setEditingDatasetItemIndex] = useState<number | null>(null);
  const [datasetItemModalOpen, setDatasetItemModalOpen] = useState(false);
  const [datasetItemDraft, setDatasetItemDraft] = useState<EvaluationDatasetItem | null>(null);
  const [savingDatasetItem, setSavingDatasetItem] = useState(false);
  const [cleanOptions, setCleanOptions] = useState<CleanOptions>({
    trim_lines: true,
    normalize_spaces: true,
    merge_blank_lines: true,
    merge_broken_lines: false
  });

  useEffect(() => {
    void refreshEvalAssets();
  }, []);

  useEffect(() => {
    setMode(initialMode);
    setStep(0);
    setActiveRun(null);
    setActiveRetrievedItem(null);
    setActiveEvalDocument(null);
    setActiveEvalDocumentRuns([]);
    setActiveEvalDocumentRun(null);
    setActiveEvalRunChunks([]);
    setActiveDataset(null);
  }, [initialMode]);

  async function refreshEvalAssets() {
    setLoadingEvalAssets(true);
    try {
      const [docs, datasets] = await Promise.all([listEvaluationDocuments(), listEvaluationDatasets()]);
      setEvalDocuments(docs);
      setEvalDatasets(datasets);
      if (!datasetId && datasets[0]?.id) setDatasetId(datasets[0].id);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取评测资产失败");
    } finally {
      setLoadingEvalAssets(false);
    }
  }
  const [splitOptions, setSplitOptions] = useState<SplitOptions>({
    chunk_size: 500,
    chunk_overlap: 100,
    attach_title: true,
    strategy: "fixed",
    separator_preset: "general"
  });
  const [retrievalOptions, setRetrievalOptions] = useState<RetrievalOptions>({
    top_k: 10,
    recall_k: 15,
    mode: "hybrid",
    rrf_k: 60
  });

  function backToList() {
    setMode("list");
    setStep(0);
    setActiveRun(null);
    setActiveRetrievedItem(null);
  }

  function showBackButton() {
    return mode === "create" || mode === "detail" || mode === "documentDetail" || mode === "documentRunChunks" || mode === "datasetEdit";
  }

  function handleEvalBack() {
    if (mode === "documentRunChunks") {
      setMode("documentDetail");
      setActiveEvalDocumentRun(null);
      setActiveEvalRunChunks([]);
      return;
    }
    if (mode === "documentDetail") {
      setMode("documents");
      setActiveEvalDocument(null);
      setActiveEvalDocumentRuns([]);
      setActiveEvalDocumentRun(null);
      setActiveEvalRunChunks([]);
      return;
    }
    if (mode === "datasetEdit") {
      setMode("datasets");
      setActiveDataset(null);
      return;
    }
    backToList();
  }

  function evalBackLabel() {
    if (mode === "documentRunChunks") return "返回文档详情";
    if (mode === "documentDetail") return "返回评测文档";
    if (mode === "datasetEdit") return "返回评测集";
    return "返回评测记录";
  }

  function breadcrumbItems() {
    const evalBase = { title: "评测工作" };
    if (mode === "list" || mode === "create" || mode === "detail") {
      if (mode === "create") return [evalBase, { title: "评测记录" }, { title: "新建评测" }];
      if (mode === "detail") return [evalBase, { title: "评测记录" }, { title: "评测详情" }];
      return [evalBase, { title: "评测记录" }];
    }
    if (mode === "documents" || mode === "documentDetail" || mode === "documentRunChunks") {
      if (mode === "documentRunChunks") return [evalBase, { title: "评测文档" }, { title: activeEvalDocument?.title || "文档详情" }, { title: "检索详情" }];
      if (mode === "documentDetail") return [evalBase, { title: "评测文档" }, { title: activeEvalDocument?.title || "文档详情" }];
      return [evalBase, { title: "评测文档" }];
    }
    if (mode === "datasets" || mode === "datasetEdit") {
      if (mode === "datasetEdit") return [evalBase, { title: "评测集" }, { title: activeDataset?.name || "编辑评测集" }];
      return [evalBase, { title: "评测集" }];
    }
    return [evalBase];
  }

  function pageSubtitle() {
    if (mode === "create") return "调整清洗、分块和检索策略后运行检索评测";
    if (mode === "detail") return activeRun?.name || "查看评测参数和报告";
    if (mode === "documentDetail") return activeEvalDocument?.title || activeEvalDocument?.filename || "";
    if (mode === "documentRunChunks") return activeEvalDocumentRun?.name || "";
    if (mode === "datasetEdit") return activeDataset?.name || "";
    if (mode === "list") return `${evaluations.length} 条评测记录`;
    if (mode === "documents") return `${evalDocuments.length} 个评测文档`;
    if (mode === "datasets") return `${evalDatasets.length} 个评测集`;
    return "";
  }

  async function openDetail(run: EvaluationRun) {
    setMode("detail");
    setLoadingDetail(true);
    try {
      setActiveRun(await getEvaluation(run.id));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取评测详情失败");
      setMode("list");
    } finally {
      setLoadingDetail(false);
    }
  }

  async function submitEvaluation() {
    if (!datasetId) {
      message.warning("请先选择评测集");
      return;
    }
    setRunning(true);
    try {
      const result = await runEvaluation({
        name,
        dataset_id: datasetId,
        document_ids: selectedDocIds,
        clean_options: cleanOptions,
        split_options: splitOptions,
        retrieval_options: retrievalOptions
      });
      message.success("评测完成");
      setActiveRun(result);
      setMode("detail");
      await onRefreshEvaluations();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "评测运行失败");
    } finally {
      setRunning(false);
    }
  }

  function createBlankDataset() {
    setActiveDataset({
      id: `draft_${crypto.randomUUID()}`,
      name: `新评测集 ${new Date().toLocaleString("zh-CN", { hour12: false })}`,
      item_count: 0,
      items: []
    });
    setMode("datasetEdit");
  }

  function isDraftDataset(dataset: EvaluationDataset) {
    return dataset.id.startsWith("draft_");
  }

  function updateDatasetItem(index: number, patch: Partial<EvaluationDatasetItem>) {
    setActiveDataset((current) => {
      if (!current) return current;
      const items = [...(current.items || [])];
      items[index] = { ...items[index], ...patch };
      return { ...current, items };
    });
  }

  function createBlankDatasetItem(): EvaluationDatasetItem {
    return {
      id: `Q${String((activeDataset?.items || []).length + 1).padStart(3, "0")}`,
      question: "",
      expected_answer: "",
      expected_source_ids: [],
      expected_evidence: "",
      should_refuse: false,
      focus: "",
      note: ""
    };
  }

  function openDatasetItemModal(index: number | null) {
    setEditingDatasetItemIndex(index);
    setDatasetItemDraft(index === null ? createBlankDatasetItem() : { ...(activeDataset?.items || [])[index] });
    setDatasetItemModalOpen(true);
  }

  async function saveDatasetItem() {
    if (!activeDataset || !datasetItemDraft) return;
    if (!datasetItemDraft.id.trim() || !datasetItemDraft.question.trim()) {
      message.warning("请填写题目 ID 和用户问题");
      return;
    }
    setSavingDatasetItem(true);
    try {
      const items = [...(activeDataset.items || [])];
      if (editingDatasetItemIndex === null) {
        items.push(datasetItemDraft);
      } else {
        items[editingDatasetItemIndex] = datasetItemDraft;
      }
      if (isDraftDataset(activeDataset)) {
        setActiveDataset({ ...activeDataset, items, item_count: items.length });
        setDatasetItemModalOpen(false);
        setDatasetItemDraft(null);
        setEditingDatasetItemIndex(null);
        message.success("问题记录已加入草稿");
        return;
      }
      const saved = await updateEvaluationDataset(activeDataset.id, { name: activeDataset.name, items });
      setActiveDataset(saved);
      setDatasetItemModalOpen(false);
      setDatasetItemDraft(null);
      setEditingDatasetItemIndex(null);
      message.success("问题记录已保存");
      await refreshEvalAssets();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "保存问题记录失败");
    } finally {
      setSavingDatasetItem(false);
    }
  }

  async function deleteDatasetItem(index: number) {
    if (!activeDataset) return;
    const items = (activeDataset.items || []).filter((_item, itemIndex) => itemIndex !== index);
    if (isDraftDataset(activeDataset)) {
      setActiveDataset({ ...activeDataset, items, item_count: items.length });
      message.success("问题记录已删除");
      return;
    }
    const saved = await updateEvaluationDataset(activeDataset.id, { name: activeDataset.name, items });
    setActiveDataset(saved);
    message.success("问题记录已删除");
    await refreshEvalAssets();
  }

  async function openEvalDocument(record: EvaluationDocument) {
    setMode("documentDetail");
    setLoadingEvalDocumentRuns(true);
    setActiveEvalDocumentRun(null);
    setActiveEvalRunChunks([]);
    try {
      const [detail, runs] = await Promise.all([
        getEvaluationDocument(record.id),
        listEvaluationDocumentRuns(record.id)
      ]);
      setActiveEvalDocument(detail);
      setActiveEvalDocumentRuns(runs);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取评测文档失败");
    } finally {
      setLoadingEvalDocumentRuns(false);
    }
  }

  async function openEvalDocumentRunChunks(run: EvaluationDocumentRun) {
    if (!activeEvalDocument) return;
    setMode("documentRunChunks");
    setActiveEvalDocumentRun(run);
    setLoadingEvalRunChunks(true);
    try {
      setActiveEvalRunChunks(await listEvaluationDocumentRunChunks(activeEvalDocument.id, run.id));
    } catch (error) {
      setActiveEvalRunChunks([]);
      message.error(error instanceof Error ? error.message : "读取评测分块失败");
    } finally {
      setLoadingEvalRunChunks(false);
    }
  }

  function datasetSourceOptions() {
    return [
      JOB_SOURCE_OPTION,
      ...evalDocuments.map((doc) => ({ value: doc.id, label: doc.title || doc.filename }))
    ];
  }

  function renderExpectedSources(value: string[] = []) {
    if (!value.length) return "未设置";
    const hasJobs = value.includes(JOB_SOURCE_ID);
    const docCount = value.filter((item) => item !== JOB_SOURCE_ID).length;
    if (hasJobs && docCount) return `岗位库 + ${docCount} 个文档`;
    if (hasJobs) return "岗位库（ES）";
    return `${docCount} 个文档`;
  }

  return (
    <section className="view-shell knowledge-view">
      <header className="panel-header knowledge-header">
        <div className="knowledge-title">
          {showBackButton() && (
            <div className="page-nav-row">
              <Button
                type="text"
                icon={<ArrowLeftOutlined />}
                onClick={handleEvalBack}
                className="back-button"
              >
                {evalBackLabel()}
              </Button>
              <Breadcrumb className="page-breadcrumb" items={breadcrumbItems()} />
            </div>
          )}
          {!showBackButton() && (
            <div className="page-nav-row">
              <Breadcrumb className="page-breadcrumb" items={breadcrumbItems()} />
            </div>
          )}
          <div className="page-title-block">
            <Title level={3}>
              {mode === "create"
                ? "新建评测"
                : mode === "detail"
                  ? "评测详情"
                  : mode === "documents" || mode === "documentDetail" || mode === "documentRunChunks"
                    ? "评测文档"
                    : mode === "datasets" || mode === "datasetEdit"
                      ? "评测集"
                      : "评测工作"}
            </Title>
            <Text type={evaluationError && mode === "list" ? "danger" : "secondary"} className="page-subtitle">
              {evaluationError && mode === "list" ? evaluationError : pageSubtitle()}
            </Text>
          </div>
        </div>
        <Space wrap>
          {mode === "list" && (
            <Button icon={<ReloadOutlined />} onClick={onRefreshEvaluations}>
              刷新
            </Button>
          )}
        </Space>
      </header>

      {mode === "list" && (
        <main className="knowledge-table-page">
          <div className="knowledge-table-head">
            <div>
              <Title level={4}>评测记录</Title>
              <Text type="secondary">每次评测保留独立历史索引，删除记录时会同时删除对应索引。</Text>
            </div>
            <Space>
              <Button icon={<PlusOutlined />} onClick={() => setMode("create")} type="primary">
                新建评测
              </Button>
            </Space>
          </div>
          <Table<EvaluationRun>
            className="knowledge-table"
            dataSource={evaluations}
            loading={loadingEvaluations}
            locale={{ emptyText: <Empty description="还没有评测记录" /> }}
            pagination={false}
            rowKey="id"
            onRow={(record) => ({ onClick: () => void openDetail(record) })}
            columns={[
              { title: "#", width: 54, render: (_value, _record, index) => index + 1 },
              {
                title: "名称",
                dataIndex: "name",
                render: (value: string, run) => (
                  <Space direction="vertical" size={0}>
                    <Text strong>{value}</Text>
                    <Text type="secondary">{run.dataset_path}</Text>
                  </Space>
                )
              },
              {
                title: "问题数",
                width: 100,
                render: (_value, run) => <Text>{String(run.summary?.question_count ?? "-")}</Text>
              },
              {
                title: "文档命中率",
                width: 120,
                render: (_value, run) => <Text>{formatRate(run.summary?.source_hit_rate)}</Text>
              },
              {
                title: "证据命中率",
                width: 120,
                render: (_value, run) => <Text>{formatRate(run.summary?.evidence_hit_rate)}</Text>
              },
              {
                title: "拒答通过率",
                width: 120,
                render: (_value, run) => <Text>{formatRate(run.summary?.refusal_hit_rate)}</Text>
              },
              {
                title: "总通过率",
                width: 100,
                render: (_value, run) => <Text>{formatRate(run.summary?.pass_rate)}</Text>
              },
              {
                title: "MRR",
                width: 90,
                render: (_value, run) => <Text>{String(run.summary?.mrr ?? "-")}</Text>
              },
              {
                title: "状态",
                width: 100,
                render: (_value, run) => <Tag color={run.status === "completed" ? "success" : run.status === "failed" ? "error" : "processing"}>{evalStatusLabel(run.status)}</Tag>
              },
              {
                title: "创建时间",
                dataIndex: "created_at",
                width: 180,
                render: (value: string) => formatDate(value)
              },
              {
                title: "操作",
                width: 110,
                render: (_value, run) => (
                  <Popconfirm
                    cancelText="取消"
                    okButtonProps={{ danger: true }}
                    okText="删除"
                    onConfirm={() => onDeleteEvaluation(run)}
                    title={`确认删除“${run.name}”？`}
                    description="会同时删除这条评测对应的历史索引。"
                  >
                    <Button danger size="small" type="link" onClick={(event) => event.stopPropagation()}>
                      删除
                    </Button>
                  </Popconfirm>
                )
              }
            ]}
          />
        </main>
      )}

      {mode === "create" && (
        <main className="ingest-panel">
          <Steps
            current={step}
            items={[
              { title: "评测范围" },
              { title: "清洗策略" },
              { title: "分块策略" },
              { title: "检索策略" },
              { title: "确认运行" }
            ]}
          />
          <section className="ingest-section">
            <div className="eval-step-panel">
              {step === 0 && (
                <>
                  <label>
                    <Text strong>评测名称</Text>
                    <Input value={name} onChange={(event) => setName(event.target.value)} />
                  </label>
                  <label>
                    <Text strong>评测集</Text>
                    <Select
                      loading={loadingEvalAssets}
                      options={evalDatasets.map((dataset) => ({ value: dataset.id, label: `${dataset.name}（${dataset.item_count ?? dataset.items?.length ?? 0}题）` }))}
                      placeholder="请选择评测集"
                      value={datasetId || undefined}
                      onChange={setDatasetId}
                    />
                  </label>
                  <div>
                    <div className="eval-section-title">
                      <Text strong>文档范围</Text>
                      <Button size="small" onClick={refreshEvalAssets}>
                        刷新评测文档
                      </Button>
                    </div>
                    <Checkbox.Group
                      className="eval-document-grid"
                      value={selectedDocIds}
                      onChange={(values) => setSelectedDocIds(values.map(String))}
                    >
                      {evalDocuments.map((doc) => (
                        <Checkbox key={doc.id} value={doc.id}>
                          {doc.title || doc.filename}
                        </Checkbox>
                      ))}
                    </Checkbox.Group>
                    <Text type="secondary">不勾选时默认评测全部评测文档。</Text>
                  </div>
                </>
              )}
              {step === 1 && (
                <div className="eval-option-grid">
                  {renderCleanCheckbox("去除行首尾空白", "trim_lines")}
                  {renderCleanCheckbox("规范连续空格", "normalize_spaces")}
                  {renderCleanCheckbox("合并多余空行", "merge_blank_lines")}
                  {renderCleanCheckbox("合并断行", "merge_broken_lines")}
                </div>
              )}
              {step === 2 && (
                <div className="eval-option-grid">
                  <label>
                    <Text strong>分块策略</Text>
                    <Select
                      value={splitOptions.strategy}
                      options={[
                        { value: "fixed", label: "固定长度" },
                        { value: "structure", label: "结构感知" },
                        { value: "recursive", label: "递归分块" }
                      ]}
                      onChange={(value) =>
                        setSplitOptions({
                          ...splitOptions,
                          strategy: value as SplitOptions["strategy"],
                          chunk_overlap: value === "structure" ? 0 : splitOptions.chunk_overlap
                        })
                      }
                    />
                  </label>
                  <label>
                    <Text strong>分块长度</Text>
                    <InputNumber min={50} max={3000} value={splitOptions.chunk_size} onChange={(value) => setSplitOptions({ ...splitOptions, chunk_size: Number(value || 500) })} />
                  </label>
                  <label>
                    <Text strong>重叠长度{splitOptions.strategy === "structure" ? "（建议为0）" : ""}</Text>
                    <InputNumber min={0} max={1000} value={splitOptions.chunk_overlap} onChange={(value) => setSplitOptions({ ...splitOptions, chunk_overlap: Number(value || 0) })} />
                  </label>
                  {splitOptions.strategy === "recursive" && (
                    <label>
                      <Text strong>分隔符预设</Text>
                      <Select
                        value={splitOptions.separator_preset}
                        options={[
                          { value: "general", label: "通用（中英混合）" },
                          { value: "chinese", label: "中文优先" },
                          { value: "english", label: "英文优先" }
                        ]}
                        onChange={(value) => setSplitOptions({ ...splitOptions, separator_preset: value as SplitOptions["separator_preset"] })}
                      />
                    </label>
                  )}
                  <Checkbox checked={splitOptions.attach_title} onChange={(event) => setSplitOptions({ ...splitOptions, attach_title: event.target.checked })}>
                    附加文档标题
                  </Checkbox>
                </div>
              )}
              {step === 3 && (
                <div className="eval-option-grid">
                  <label>
                    <Text strong>检索模式</Text>
                    <Select
                      value={retrievalOptions.mode}
                      options={[
                        { value: "hybrid", label: "混合检索" },
                        { value: "vector", label: "向量检索" },
                        { value: "keyword", label: "关键词检索" }
                      ]}
                      onChange={(value) => setRetrievalOptions({ ...retrievalOptions, mode: value })}
                    />
                  </label>
                  <label>
                    <Text strong>Top K</Text>
                    <InputNumber min={1} max={20} value={retrievalOptions.top_k} onChange={(value) => setRetrievalOptions({ ...retrievalOptions, top_k: Number(value || 5) })} />
                  </label>
                  <label>
                    <Text strong>每路召回数 (recall_k)</Text>
                    <InputNumber min={1} max={50} value={retrievalOptions.recall_k} onChange={(value) => setRetrievalOptions({ ...retrievalOptions, recall_k: Number(value || 15) })} />
                  </label>
                  <label>
                    <Text strong>RRF 平滑参数 (k)</Text>
                    <InputNumber min={1} max={120} value={retrievalOptions.rrf_k} onChange={(value) => setRetrievalOptions({ ...retrievalOptions, rrf_k: Number(value || 60) })} />
                  </label>
                </div>
              )}
              {step === 4 && (
                <div className="eval-confirm">
                  <Descriptions bordered column={1} size="small">
                    <Descriptions.Item label="评测名称">{name}</Descriptions.Item>
                    <Descriptions.Item label="评测集">{evalDatasets.find((dataset) => dataset.id === datasetId)?.name || datasetId || "未选择"}</Descriptions.Item>
                    <Descriptions.Item label="文档范围">{selectedDocIds.length ? `${selectedDocIds.length} 个评测文档` : "全部评测文档"}</Descriptions.Item>
                    <Descriptions.Item label="清洗策略">{JSON.stringify(cleanOptions)}</Descriptions.Item>
                    <Descriptions.Item label="分块策略">
                      {{
                        fixed: "固定长度",
                        structure: "结构感知",
                        recursive: "递归分块"
                      }[splitOptions.strategy]} / 长度 {splitOptions.chunk_size} / 重叠 {splitOptions.chunk_overlap}
                      {splitOptions.strategy === "recursive" ? ` / 分隔符 ${splitOptions.separator_preset === "chinese" ? "中文" : splitOptions.separator_preset === "english" ? "英文" : "通用"}` : ""}
                      {splitOptions.attach_title ? " / 附标题" : ""}
                    </Descriptions.Item>
                    <Descriptions.Item label="检索策略">{JSON.stringify(retrievalOptions)}</Descriptions.Item>
                  </Descriptions>
                </div>
              )}
            </div>
          </section>
          <div className="eval-step-actions">
            <Button disabled={step === 0 || running} onClick={() => setStep((value) => Math.max(value - 1, 0))}>
              上一步
            </Button>
            {step < 4 ? (
              <Button type="primary" onClick={() => setStep((value) => Math.min(value + 1, 4))}>
                下一步
              </Button>
            ) : (
              <Button loading={running} type="primary" onClick={submitEvaluation}>
                开始评测
              </Button>
            )}
          </div>
        </main>
      )}

      {mode === "documents" && (
        <main className="knowledge-table-page">
          <div className="knowledge-table-head">
            <div>
              <Title level={4}>评测文档</Title>
              <Text type="secondary">评测专用文档，不参与正式知识库问答。</Text>
            </div>
            <Space>
              <Upload
                accept=".txt,.pdf,.md"
                customRequest={({ file, onError, onSuccess }: UploadRequestOption) => {
                  setUploadingEvalDocuments(true);
                  message.loading({ content: "正在上传评测文档...", key: "eval-doc-upload", duration: 0 });
                  uploadEvaluationDocuments([file as File])
                    .then(async (data) => {
                      onSuccess?.(data);
                      message.success({ content: "评测文档已上传", key: "eval-doc-upload" });
                      await refreshEvalAssets();
                    })
                    .catch((error) => {
                      message.error({ content: error instanceof Error ? error.message : "上传评测文档失败", key: "eval-doc-upload" });
                      onError?.(error);
                    })
                    .finally(() => setUploadingEvalDocuments(false));
                }}
                multiple
                showUploadList={false}
              >
                <Button icon={<UploadOutlined />} loading={uploadingEvalDocuments} type="primary">上传评测文档</Button>
              </Upload>
              <Button icon={<ReloadOutlined />} onClick={refreshEvalAssets}>刷新</Button>
            </Space>
          </div>
          <Table<EvaluationDocument>
            className="knowledge-table"
            dataSource={evalDocuments}
            loading={loadingEvalAssets}
            locale={{ emptyText: <Empty description="还没有评测文档" /> }}
            pagination={false}
            rowKey="id"
            onRow={(record) => ({
              onClick: () => void openEvalDocument(record)
            })}
            columns={[
              { title: "#", width: 54, render: (_value, _record, index) => index + 1 },
              { title: "名称", dataIndex: "title", render: (_value, doc) => <Text strong>{doc.title || doc.filename}</Text> },
              { title: "类型", dataIndex: "file_type", width: 100, render: (value) => <Tag>{String(value).toUpperCase()}</Tag> },
              { title: "基准分块", dataIndex: "chunk_count", width: 120 },
              {
                title: "最新评测分块",
                dataIndex: "latest_eval_chunk_count",
                width: 140,
                render: (value: number | null | undefined, doc) =>
                  value === null || value === undefined ? (
                    <Text type="secondary">暂无</Text>
                  ) : (
                    <Space size={4}>
                      <Text>{value}</Text>
                      {doc.latest_eval_run_name && <Text type="secondary">({doc.latest_eval_run_name})</Text>}
                    </Space>
                  )
              },
              { title: "上传时间", dataIndex: "created_at", width: 180, render: (value: string) => formatDate(value) },
              {
                title: "操作",
                width: 100,
                render: (_value, doc) => (
                  <Popconfirm
                    cancelText="取消"
                    okButtonProps={{ danger: true }}
                    okText="删除"
                    onConfirm={async (event) => {
                      event?.stopPropagation();
                      await deleteEvaluationDocument(doc.id);
                      message.success("评测文档已删除");
                      await refreshEvalAssets();
                    }}
                    title={`确认删除“${doc.title || doc.filename}”？`}
                  >
                    <Button danger size="small" type="link" onClick={(event) => event.stopPropagation()}>删除</Button>
                  </Popconfirm>
                )
              }
            ]}
          />
        </main>
      )}

      {mode === "documentDetail" && (
        <main className="document-chunks-page">
          <div className="document-chunks-page-head">
            <div>
              <Title level={4}>{activeEvalDocument?.title || "评测文档"}</Title>
              <Text type="secondary">
                {loadingEvalDocumentRuns ? "正在读取关联评测记录" : `${activeEvalDocumentRuns.length} 条关联评测记录`}
              </Text>
            </div>
          </div>
          <Table<EvaluationDocumentRun>
            className="knowledge-table"
            dataSource={activeEvalDocumentRuns}
            loading={loadingEvalDocumentRuns}
            locale={{ emptyText: <Empty description="该文档还没有参与评测记录" /> }}
            pagination={false}
            rowKey="id"
            onRow={(record) => ({
              onClick: () => void openEvalDocumentRunChunks(record)
            })}
            columns={[
              { title: "#", width: 54, render: (_value, _record, index) => index + 1 },
              { title: "评测记录", dataIndex: "name", render: (value) => <Text strong>{String(value)}</Text> },
              { title: "状态", dataIndex: "status", width: 100, render: (value) => <Tag>{evalStatusLabel(String(value))}</Tag> },
              { title: "分块数量", dataIndex: "chunk_count", width: 110 },
              {
                title: "分块策略",
                dataIndex: "split_options",
                width: 210,
                render: (value: Partial<SplitOptions>) => {
                  const strategy = value?.strategy || "fixed";
                  const labels: Record<string, string> = { fixed: "固定", structure: "结构", recursive: "递归" };
                  return `${labels[strategy] || strategy} / ${value?.chunk_size ?? "-"} / ${value?.chunk_overlap ?? "-"}`;
                }
              },
              { title: "评测时间", dataIndex: "created_at", width: 180, render: (value: string) => formatDate(value) }
            ]}
          />
        </main>
      )}

      {mode === "documentRunChunks" && (
        <main className="document-chunks-page">
          <div className="document-chunks-page-head">
            <div>
              <Title level={4}>{activeEvalDocumentRun?.name || "评测分块"}</Title>
              <Text type="secondary">
                {loadingEvalRunChunks ? "正在读取分块" : `${activeEvalRunChunks.length} 个历史分块`}
              </Text>
            </div>
          </div>
          <List
            className="chunk-list chunk-page-list"
            dataSource={activeEvalRunChunks}
            loading={loadingEvalRunChunks}
            locale={{ emptyText: <Empty description="暂无分块" /> }}
            renderItem={(chunk) => (
              <List.Item className="chunk-list-item chunk-page-item">
                <List.Item.Meta
                  title={
                    <Space wrap>
                      <Tag>片段 {String(chunk.metadata.chunk_index ?? "")}</Tag>
                      <Text type="secondary">{chunk.length} 字</Text>
                      {chunk.metadata.page !== undefined && chunk.metadata.page !== null && (
                        <Text type="secondary">页码 {String(chunk.metadata.page)}</Text>
                      )}
                      {Array.isArray(chunk.metadata.heading_path) && (chunk.metadata.heading_path as string[]).length > 0 && (
                        <Text type="secondary" style={{ fontSize: 12 }}>{(chunk.metadata.heading_path as string[]).join(" > ")}</Text>
                      )}
                    </Space>
                  }
                  description={<Text className="chunk-preview">{chunk.text}</Text>}
                />
              </List.Item>
            )}
          />
        </main>
      )}

      {mode === "datasets" && (
        <main className="knowledge-table-page">
          <div className="knowledge-table-head">
            <div>
              <Title level={4}>评测集</Title>
              <Text type="secondary">评测集使用评测文档和证据文本作为命中标准，不再绑定 chunk_id。</Text>
            </div>
            <Space>
              <Button icon={<PlusOutlined />} onClick={createBlankDataset} type="primary">
                新建评测集
              </Button>
              <Upload
                accept=".csv"
                customRequest={({ file, onError, onSuccess }: UploadRequestOption) => {
                  setImportingDataset(true);
                  message.loading({ content: "正在导入评测集...", key: "dataset-import", duration: 0 });
                  importEvaluationDataset(file as File)
                    .then(async (data) => {
                      onSuccess?.(data);
                      message.success({ content: "评测集已导入", key: "dataset-import" });
                      await refreshEvalAssets();
                    })
                    .catch((error) => {
                      message.error({ content: error instanceof Error ? error.message : "导入评测集失败", key: "dataset-import" });
                      onError?.(error);
                    })
                    .finally(() => setImportingDataset(false));
                }}
                maxCount={1}
                showUploadList={false}
              >
                <Button icon={<UploadOutlined />} loading={importingDataset} type="primary">导入评测集</Button>
              </Upload>
              <Button icon={<ReloadOutlined />} onClick={refreshEvalAssets}>刷新</Button>
            </Space>
          </div>
          <Table<EvaluationDataset>
            className="knowledge-table"
            dataSource={evalDatasets}
            loading={loadingEvalAssets}
            locale={{ emptyText: <Empty description="还没有评测集" /> }}
            pagination={false}
            rowKey="id"
            onRow={(record) => ({
              onClick: async () => {
                setActiveDataset(await getEvaluationDataset(record.id));
                setMode("datasetEdit");
              }
            })}
            columns={[
              { title: "#", width: 54, render: (_value, _record, index) => index + 1 },
              { title: "名称", dataIndex: "name", render: (value) => <Text strong>{String(value)}</Text> },
              { title: "题目数", dataIndex: "item_count", width: 100 },
              { title: "更新时间", dataIndex: "updated_at", width: 180, render: (value: string) => formatDate(value) },
              {
                title: "操作",
                width: 180,
                render: (_value, dataset) => (
                  <Space size={4} onClick={(event) => event.stopPropagation()}>
                    <Button
                      size="small"
                      type="link"
                      onClick={async () => {
                        try {
                          const blob = await exportEvaluationDataset(dataset.id);
                          const url = URL.createObjectURL(blob);
                          const anchor = document.createElement("a");
                          anchor.href = url;
                          anchor.download = `${dataset.name}.csv`;
                          anchor.click();
                          URL.revokeObjectURL(url);
                        } catch (error) {
                          message.error(error instanceof Error ? error.message : "导出评测集失败");
                        }
                      }}
                    >
                      导出
                    </Button>
                    <Popconfirm
                      cancelText="取消"
                      okButtonProps={{ danger: true }}
                      okText="删除"
                      onConfirm={async () => {
                        await deleteEvaluationDataset(dataset.id);
                        message.success("评测集已删除");
                        await refreshEvalAssets();
                      }}
                      title={`确认删除“${dataset.name}”？`}
                    >
                      <Button danger size="small" type="link">删除</Button>
                    </Popconfirm>
                  </Space>
                )
              }
            ]}
          />
        </main>
      )}

      {mode === "datasetEdit" && (
        <main className="eval-detail-page">
          {!activeDataset ? (
            <Empty description="正在读取评测集" />
          ) : (
            <section className="eval-detail-card">
              <div className="ingest-card-header">
                <Input
                  value={activeDataset.name}
                  onChange={(event) => setActiveDataset({ ...activeDataset, name: event.target.value })}
                />
                <Space>
                  {isDraftDataset(activeDataset) && <Tag color="warning">未保存</Tag>}
                  <Button icon={<PlusOutlined />} onClick={() => openDatasetItemModal(null)} type="primary">
                    新增问题记录
                  </Button>
                  <Button
                    onClick={async () => {
                      const saved = isDraftDataset(activeDataset)
                        ? await createEvaluationDataset({
                            name: activeDataset.name,
                            items: activeDataset.items || []
                          })
                        : await updateEvaluationDataset(activeDataset.id, {
                            name: activeDataset.name,
                            items: activeDataset.items || []
                          });
                      setActiveDataset(saved);
                      message.success("评测集已保存");
                      await refreshEvalAssets();
                    }}
                  >
                    {isDraftDataset(activeDataset) ? "保存评测集" : "保存名称"}
                  </Button>
                </Space>
              </div>
              <Table<EvaluationDatasetItem>
                className="knowledge-table"
                dataSource={activeDataset.items || []}
                locale={{ emptyText: <Empty description="还没有问题记录" /> }}
                pagination={false}
                rowKey={(item, index) => `${item.id}-${index}`}
                onRow={(_record, index) => ({
                  onClick: () => openDatasetItemModal(index ?? null)
                })}
                columns={[
                  { title: "#", width: 54, render: (_value, _record, index) => index + 1 },
                  { title: "ID", dataIndex: "id", width: 100 },
                  {
                    title: "用户问题",
                    dataIndex: "question",
                    ellipsis: true,
                    render: (value) => <Text strong>{String(value || "-")}</Text>
                  },
                  {
                    title: "期望来源",
                    dataIndex: "expected_source_ids",
                    width: 220,
                    render: (value: string[]) => renderExpectedSources(value)
                  },
                  {
                    title: "是否拒答",
                    dataIndex: "should_refuse",
                    width: 100,
                    render: (value: boolean) => (value ? <Tag color="warning">是</Tag> : <Tag>否</Tag>)
                  },
                  {
                    title: "评测重点",
                    dataIndex: "focus",
                    width: 220,
                    ellipsis: true,
                    render: (value) => String(value || "-")
                  },
                  {
                    title: "操作",
                    width: 150,
                    render: (_value, _item, index) => (
                      <Space size={4} onClick={(event) => event.stopPropagation()}>
                        <Button size="small" type="link" onClick={() => openDatasetItemModal(index)}>
                          编辑
                        </Button>
                        <Popconfirm
                          cancelText="取消"
                          okButtonProps={{ danger: true }}
                          okText="删除"
                          onConfirm={() => deleteDatasetItem(index)}
                          title="确认删除这条问题记录？"
                        >
                          <Button danger size="small" type="link">
                            删除
                          </Button>
                        </Popconfirm>
                      </Space>
                    )
                  }
                ]}
              />
              <Modal
                confirmLoading={savingDatasetItem}
                destroyOnClose
                okText="保存"
                onCancel={() => {
                  if (!savingDatasetItem) {
                    setDatasetItemModalOpen(false);
                    setDatasetItemDraft(null);
                    setEditingDatasetItemIndex(null);
                  }
                }}
                onOk={saveDatasetItem}
                open={datasetItemModalOpen}
                title={editingDatasetItemIndex === null ? "新增问题记录" : "编辑问题记录"}
                width={760}
              >
                {datasetItemDraft && (
                  <div className="dataset-edit-grid dataset-item-modal-grid">
                    <label>
                      <Text type="secondary">ID</Text>
                      <Input
                        value={datasetItemDraft.id}
                        placeholder="题目 ID"
                        onChange={(event) => setDatasetItemDraft({ ...datasetItemDraft, id: event.target.value })}
                      />
                    </label>
                    <label className="span-2">
                      <Text type="secondary">用户问题</Text>
                      <Input
                        value={datasetItemDraft.question}
                        placeholder="用户会怎么问"
                        onChange={(event) => setDatasetItemDraft({ ...datasetItemDraft, question: event.target.value })}
                      />
                    </label>
                    <label className="span-3">
                      <Text type="secondary">期望答案要点</Text>
                      <Input.TextArea
                        value={datasetItemDraft.expected_answer || ""}
                        placeholder="回答里应该覆盖的要点"
                        autoSize={{ minRows: 2, maxRows: 5 }}
                        onChange={(event) => setDatasetItemDraft({ ...datasetItemDraft, expected_answer: event.target.value })}
                      />
                    </label>
                    <label className="span-3">
                      <Text type="secondary">期望来源评测文档</Text>
                      <Select
                        mode="multiple"
                        value={datasetItemDraft.expected_source_ids}
                        placeholder="选择应该被召回的评测文档或岗位库"
                        options={datasetSourceOptions()}
                        onChange={(value) => setDatasetItemDraft({ ...datasetItemDraft, expected_source_ids: value })}
                      />
                    </label>
                    <label className="span-3">
                      <Text type="secondary">期望证据文本</Text>
                      <Input.TextArea
                        value={datasetItemDraft.expected_evidence || ""}
                        placeholder="用于判断召回文本是否命中的关键原文"
                        autoSize={{ minRows: 3, maxRows: 8 }}
                        onChange={(event) => setDatasetItemDraft({ ...datasetItemDraft, expected_evidence: event.target.value })}
                      />
                    </label>
                    <label>
                      <Text type="secondary">是否应拒答</Text>
                      <Checkbox
                        checked={Boolean(datasetItemDraft.should_refuse)}
                        onChange={(event) => setDatasetItemDraft({ ...datasetItemDraft, should_refuse: event.target.checked })}
                      >
                        应拒答
                      </Checkbox>
                    </label>
                    <label className="span-2">
                      <Text type="secondary">评测重点</Text>
                      <Input
                        value={datasetItemDraft.focus || ""}
                        placeholder="例如来源命中、排序、岗位字段覆盖"
                        onChange={(event) => setDatasetItemDraft({ ...datasetItemDraft, focus: event.target.value })}
                      />
                    </label>
                    <label className="span-3">
                      <Text type="secondary">备注</Text>
                      <Input.TextArea
                        value={datasetItemDraft.note || ""}
                        placeholder="可选备注"
                        autoSize={{ minRows: 2, maxRows: 4 }}
                        onChange={(event) => setDatasetItemDraft({ ...datasetItemDraft, note: event.target.value })}
                      />
                    </label>
                  </div>
                )}
              </Modal>
            </section>
          )}
        </main>
      )}

      {mode === "detail" && (
        <main className="eval-detail-page">
          {loadingDetail || !activeRun ? (
            <Empty description="正在读取评测详情" />
          ) : (
            <>
              <section className="eval-summary-grid">
                <StatTile label="问题数" value={String(activeRun.summary?.question_count ?? "-")} />
                <StatTile label="文档命中率" value={formatRate(activeRun.summary?.source_hit_rate)} />
                <StatTile label="证据命中率" value={formatRate(activeRun.summary?.evidence_hit_rate)} />
                <StatTile label="拒答通过率" value={formatRate(activeRun.summary?.refusal_hit_rate)} />
                <StatTile label="总通过率" value={formatRate(activeRun.summary?.pass_rate)} />
                <StatTile label="MRR" value={String(activeRun.summary?.mrr ?? "-")} />
              </section>
              <section className="eval-detail-card">
                <Title level={4}>参数快照</Title>
                <Descriptions bordered column={2} size="small">
                  <Descriptions.Item label="历史索引">{activeRun.es_index_name}</Descriptions.Item>
                  <Descriptions.Item label="状态">{evalStatusLabel(activeRun.status)}</Descriptions.Item>
                  <Descriptions.Item label="评测集">{activeRun.dataset_path}</Descriptions.Item>
                  <Descriptions.Item label="文档范围">{JSON.stringify(activeRun.document_scope)}</Descriptions.Item>
                  <Descriptions.Item label="清洗策略">{JSON.stringify(activeRun.clean_options)}</Descriptions.Item>
                  <Descriptions.Item label="分块策略">
                    {(() => {
                      const opts = activeRun.split_options || {};
                      const strategy = String(opts.strategy || "fixed");
                      const labels: Record<string, string> = { fixed: "固定长度", structure: "结构感知", recursive: "递归分块" };
                      return `${labels[strategy] || strategy} / 长度 ${opts.chunk_size ?? "-"} / 重叠 ${opts.chunk_overlap ?? "-"}${strategy === "recursive" ? ` / ${opts.separator_preset === "chinese" ? "中文" : opts.separator_preset === "english" ? "英文" : "通用"}` : ""}${opts.attach_title ? " / 附标题" : ""}`;
                    })()}
                  </Descriptions.Item>
                  <Descriptions.Item label="检索策略">{JSON.stringify(activeRun.retrieval_options)}</Descriptions.Item>
                  {activeRun.error && <Descriptions.Item label="错误">{activeRun.error}</Descriptions.Item>}
                </Descriptions>
              </section>
              <section className="eval-detail-card">
                <Title level={4}>评测明细</Title>
                <List
                  dataSource={activeRun.items || []}
                  renderItem={(item) => (
                    <List.Item className="eval-result-item clickable" onClick={() => setActiveRetrievedItem(item)}>
                      <List.Item.Meta
                        title={
                          <Space wrap>
                            <Text strong>{item.question_id || item.id}</Text>
                            {item.should_refuse || item.metrics?.should_refuse ? (
                              <Tag color={item.metrics?.refusal_hit ? "success" : "error"}>
                                {item.metrics?.refusal_hit ? "拒答通过" : "拒答未通过"}
                              </Tag>
                            ) : (
                              <>
                                <Tag color={item.metrics?.source_hit ? "success" : "error"}>
                                  {item.metrics?.source_hit ? "文档命中" : "文档未命中"}
                                </Tag>
                                <Tag color={item.metrics?.evidence_hit ? "success" : "default"}>
                                  {item.metrics?.evidence_hit ? "证据命中" : "证据未命中"}
                                </Tag>
                              </>
                            )}
                          </Space>
                        }
                        description={
                          <div className="eval-item-body">
                            <Text>{item.question}</Text>
                            <Text type="secondary">召回：{summarizeRetrieved(item.retrieved)}</Text>
                            <Text type="secondary">点击查看本次召回结果</Text>
                          </div>
                        }
                      />
                    </List.Item>
                  )}
                />
                <Modal
                  destroyOnClose
                  footer={null}
                  onCancel={() => setActiveRetrievedItem(null)}
                  open={!!activeRetrievedItem}
                  title={activeRetrievedItem ? `召回结果：${activeRetrievedItem.question_id || activeRetrievedItem.id}` : "召回结果"}
                  width={1400}
                >
                  {activeRetrievedItem && (
                    <div className="retrieval-modal">
                      <aside className="retrieval-baseline">
                        <div className="retrieval-question">
                          <Text type="secondary">用户问题</Text>
                          <Text strong>{activeRetrievedItem.question}</Text>
                        </div>
                        <div className="baseline-block">
                          <Text type="secondary">期望答案要点</Text>
                          <pre>{activeRetrievedItem.expected_answer || "未填写"}</pre>
                        </div>
                        <div className="baseline-block">
                          <Text type="secondary">期望证据文本</Text>
                          <pre>{activeRetrievedItem.expected_chunk_text || "未填写"}</pre>
                        </div>
                        <div className="baseline-block">
                          <Text type="secondary">期望来源</Text>
                          <Space wrap>
                            {(activeRetrievedItem.expected_source_ids || []).length ? (
                              activeRetrievedItem.expected_source_ids.map((sourceId) => (
                                <Tag key={sourceId}>{sourceId === JOB_SOURCE_ID ? "岗位库（ES）" : sourceId}</Tag>
                              ))
                            ) : (
                              <Tag>未设置</Tag>
                            )}
                          </Space>
                        </div>
                        <div className="baseline-block">
                          <Text type="secondary">本题指标</Text>
                          <Space wrap>
                            {activeRetrievedItem.should_refuse || activeRetrievedItem.metrics?.should_refuse ? (
                              <>
                                <Tag color={activeRetrievedItem.metrics?.refusal_hit ? "success" : "error"}>
                                  {activeRetrievedItem.metrics?.refusal_hit ? "拒答通过" : "拒答未通过"}
                                </Tag>
                              </>
                            ) : (
                              <>
                                <Tag color={activeRetrievedItem.metrics?.source_hit ? "success" : "error"}>
                                  {activeRetrievedItem.metrics?.source_hit ? "来源命中" : "来源未命中"}
                                </Tag>
                                <Tag color={activeRetrievedItem.metrics?.evidence_hit ? "success" : "default"}>
                                  {activeRetrievedItem.metrics?.evidence_hit ? "证据命中" : "证据未命中"}
                                </Tag>
                                <Text type="secondary">证据分: {String(activeRetrievedItem.metrics?.evidence_score ?? "-")}</Text>
                              </>
                            )}
                            <Text type="secondary">MRR: {String(activeRetrievedItem.metrics?.mrr ?? "-")}</Text>
                          </Space>
                        </div>
                      </aside>
                      <section className="retrieval-results">
                        <Text strong>本次召回结果</Text>
                        <div className="baseline-block retrieval-query-block">
                          <Text type="secondary">本次检索 Query</Text>
                          {(activeRetrievedItem.retrieval_queries || []).length ? (
                            <Space direction="vertical" size={8} style={{ width: "100%" }}>
                              {(activeRetrievedItem.retrieval_queries || []).map((query, index) => (
                                <div className="retrieval-query-item" key={`${String(query.query || "")}-${index}`}>
                                  <Space wrap>
                                    <Tag>{String(query.type || "query")}</Tag>
                                    <Tag color={query.target === "jobs" ? "purple" : "blue"}>
                                      {query.target === "jobs" ? "岗位库" : "评测文档"}
                                    </Tag>
                                    <Text type="secondary">topK {String(query.top_k ?? "-")}</Text>
                                    <Text type="secondary">模式 {String(query.mode ?? "-")}</Text>
                                  </Space>
                                  <pre>{String(query.query || "")}</pre>
                                </div>
                              ))}
                            </Space>
                          ) : (
                            <pre>{activeRetrievedItem.question}</pre>
                          )}
                        </div>
                        <List
                          dataSource={activeRetrievedItem.retrieved || []}
                          locale={{ emptyText: <Empty description="本题没有召回结果" /> }}
                          renderItem={(retrieved) => {
                            const metadata = (retrieved.metadata || {}) as Record<string, unknown>;
                            const filename = String(retrieved.filename || metadata.title || metadata.filename || "未知来源");
                            const sourceType = metadata.source_type === "job" ? "岗位" : "文档";
                            return (
                              <List.Item className="retrieval-result-item">
                                <div className="retrieval-result-body">
                                  <Space wrap>
                                    <Tag color="blue">#{String(retrieved.rank ?? "-")}</Tag>
                                    <Tag>{sourceType}</Tag>
                                    <Text strong>{filename}</Text>
                                    <Text type="secondary">RRF {String(retrieved.score ?? "-")}</Text>
                                    <Text type="secondary">关键词 {String(retrieved.keyword_score ?? "-")}</Text>
                                    <Text type="secondary">向量 {String(retrieved.vector_score ?? "-")}</Text>
                                  </Space>
                                  <pre>{String(retrieved.text || "暂无文本")}</pre>
                                </div>
                              </List.Item>
                            );
                          }}
                        />
                      </section>
                    </div>
                  )}
                </Modal>
              </section>
            </>
          )}
        </main>
      )}
    </section>
  );

  function renderCleanCheckbox(label: string, key: keyof CleanOptions) {
    return (
      <Checkbox
        checked={cleanOptions[key]}
        onChange={(event) => setCleanOptions({ ...cleanOptions, [key]: event.target.checked })}
      >
        {label}
      </Checkbox>
    );
  }
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat-tile">
      <Text type="secondary">{label}</Text>
      <strong>{value}</strong>
    </div>
  );
}
