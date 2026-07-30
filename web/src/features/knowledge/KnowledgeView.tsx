import { ArrowLeftOutlined, BarChartOutlined, CheckCircleOutlined, EyeOutlined, ReloadOutlined, UploadOutlined } from "@ant-design/icons";
import { App, Button, Card, Checkbox, Col, Descriptions, Drawer, Empty, Input, InputNumber, List, Modal, Popconfirm, Row, Select, Space, Statistic, Steps, Table, Tag, Typography, Upload } from "antd";
import type { UploadRequestOption } from "rc-upload/lib/interface";
import { useEffect, useState } from "react";
import { commitDocumentStage, getDocumentStats, listDocumentChunks, previewDocumentStage, stageDocument } from "../../api";
import type { CleanOptions, DocumentChunk, DocumentInfo, DocumentMetadataInput, DocumentStage, DocumentStats, SplitOptions } from "../../types";
import { documentExt, formatDate, formatFileSize } from "../../utils";

const { Text, Title } = Typography;

export function KnowledgeView({
  documents,
  documentError,
  loadingDocuments,
  onDeleteDocument,
  onRefreshDocuments
}: {
  documents: DocumentInfo[];
  documentError: string;
  loadingDocuments: boolean;
  onDeleteDocument: (doc: DocumentInfo) => Promise<void>;
  onRefreshDocuments: () => Promise<void>;
}) {
  const { message } = App.useApp();
  const [stage, setStage] = useState<DocumentStage | null>(null);
  const [mode, setMode] = useState<"list" | "chunks" | "upload">("list");
  const [selectedDocId, setSelectedDocId] = useState<string | undefined>(documents[0]?.doc_id);
  const [replaceDoc, setReplaceDoc] = useState<DocumentInfo | null>(null);
  const [metadata, setMetadata] = useState<DocumentMetadataInput | null>(null);
  const [cleanOptions, setCleanOptions] = useState<CleanOptions | null>(null);
  const [splitOptions, setSplitOptions] = useState<SplitOptions | null>(null);
  const [step, setStep] = useState(0);
  const [stagingDocument, setStagingDocument] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [documentSearch, setDocumentSearch] = useState("");
  const [documentFilter, setDocumentFilter] = useState("all");
  const [documentSort, setDocumentSort] = useState("uploaded_desc");
  const [chunks, setChunks] = useState<DocumentChunk[]>([]);
  const [loadingChunks, setLoadingChunks] = useState(false);
  const [chunksReloadKey, setChunksReloadKey] = useState(0);
  const [activeChunk, setActiveChunk] = useState<DocumentChunk | null>(null);
  const [statsOpen, setStatsOpen] = useState(false);
  const [stats, setStats] = useState<DocumentStats | null>(null);
  const [loadingStats, setLoadingStats] = useState(false);
  const selectedDoc = documents.find((doc) => doc.doc_id === selectedDocId);
  const visibleDocuments = documents
    .filter((doc) => {
      const name = doc.filename || doc.doc_id || "";
      const keyword = documentSearch.trim().toLowerCase();
      if (documentFilter !== "all" && doc.filename && !doc.filename.toLowerCase().endsWith(documentFilter)) {
        return false;
      }
      return !keyword || name.toLowerCase().includes(keyword) || doc.doc_id.toLowerCase().includes(keyword);
    })
    .sort((a, b) => {
      if (documentSort === "name_asc") return (a.filename || "").localeCompare(b.filename || "", "zh-CN");
      if (documentSort === "chunks_desc") return (b.chunk_count || 0) - (a.chunk_count || 0);
      return new Date(b.uploaded_at || 0).getTime() - new Date(a.uploaded_at || 0).getTime();
    });

  useEffect(() => {
    if (!documents.length) {
      setSelectedDocId(undefined);
      return;
    }
    if (!selectedDocId || !documents.some((doc) => doc.doc_id === selectedDocId)) {
      setSelectedDocId(documents[0].doc_id);
    }
  }, [documents, selectedDocId]);

  useEffect(() => {
    if (mode !== "chunks" || !selectedDoc?.doc_id) {
      setChunks([]);
      return;
    }
    setLoadingChunks(true);
    listDocumentChunks(selectedDoc.doc_id)
      .then(setChunks)
      .catch((error) => {
        setChunks([]);
        message.error(error instanceof Error ? error.message : "读取分块失败");
      })
      .finally(() => setLoadingChunks(false));
  }, [mode, selectedDoc?.doc_id, chunksReloadKey, message]);

  function startUpload(doc?: DocumentInfo) {
    resetStage();
    setReplaceDoc(doc || null);
    setMode("upload");
    if (doc) {
      message.info(`将更新：${doc.filename}`);
    }
  }

  function backToList() {
    resetStage();
    setReplaceDoc(null);
    setActiveChunk(null);
    setMode("list");
  }

  function openDocumentChunks(doc: DocumentInfo) {
    setSelectedDocId(doc.doc_id);
    setActiveChunk(null);
    setMode("chunks");
  }

  async function openStats() {
    setStatsOpen(true);
    setLoadingStats(true);
    try {
      const result = await getDocumentStats();
      setStats(result);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取统计失败");
    } finally {
      setLoadingStats(false);
    }
  }

  async function handleStageFile(file: File) {
    setStagingDocument(true);
    message.loading({ content: "正在解析文档...", key: "stage-document", duration: 0 });
    try {
      const result = await stageDocument(file);
      setStage(result);
      setMetadata(result.metadata);
      setCleanOptions(result.clean_options);
      setSplitOptions(result.split_options);
      setStep(1);
      message.success({ content: "文档已解析，请填写文档信息", key: "stage-document" });
    } catch (error) {
      message.error({ content: error instanceof Error ? error.message : "文档解析失败", key: "stage-document" });
      throw error;
    } finally {
      setStagingDocument(false);
    }
  }

  async function handlePreview() {
    if (!stage || !metadata || !cleanOptions || !splitOptions) return;
    setPreviewing(true);
    try {
      const result = await previewDocumentStage({
        stage_id: stage.stage_id,
        metadata,
        clean_options: cleanOptions,
        split_options: splitOptions,
        replace_doc_id: replaceDoc?.doc_id
      });
      setStage(result);
      message.success("预览已更新");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "生成预览失败");
    } finally {
      setPreviewing(false);
    }
  }

  async function handleCommit() {
    if (!stage || !metadata || !cleanOptions || !splitOptions) return;
    setCommitting(true);
    try {
      const result = await commitDocumentStage({
        stage_id: stage.stage_id,
        metadata,
        clean_options: cleanOptions,
        split_options: splitOptions,
        replace_doc_id: replaceDoc?.doc_id
      });
      message.success(`${replaceDoc ? "更新" : "入库"}完成，生成 ${result.chunk_count} 个片段`);
      await onRefreshDocuments();
      setSelectedDocId(result.doc_id);
      backToList();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "入库失败");
    } finally {
      setCommitting(false);
    }
  }

  async function goNext(targetStep: number) {
    if (targetStep === 2 && step === 1) {
      await handlePreview();
    }
    setStep(targetStep);
  }

  function resetStage() {
    setStage(null);
    setMetadata(null);
    setCleanOptions(null);
    setSplitOptions(null);
    setStep(0);
  }

  return (
    <section className="view-shell knowledge-view">
      <header className="panel-header knowledge-header">
        <div className="knowledge-title">
          {mode === "upload" && (
            <Button icon={<ArrowLeftOutlined />} onClick={backToList} type="text">
              返回
            </Button>
          )}
          {mode === "chunks" && (
            <Button icon={<ArrowLeftOutlined />} onClick={backToList} type="text">
              返回文档列表
            </Button>
          )}
          <div>
          <Title level={3}>
            {mode === "upload"
              ? replaceDoc
                ? "更新文档"
                : "上传文档"
              : mode === "chunks"
                ? "文档分块"
                : "知识库管理"}
          </Title>
          <Text type={documentError ? "danger" : "secondary"}>
            {mode === "upload"
              ? replaceDoc
                ? `处理新文档完成后，将替换 ${replaceDoc.filename}`
                : "按步骤确认后再写入知识库"
              : mode === "chunks"
                ? selectedDoc?.filename || "查看文档分块"
                : documentError || (documents.length ? `${documents.length} 个文档` : "暂无文档")}
          </Text>
          </div>
        </div>
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={onRefreshDocuments}>
            刷新
          </Button>
        </Space>
      </header>
      {mode === "list" ? (
        <main className="knowledge-table-page">
          <div className="knowledge-table-head">
            <div>
              <Title level={4}>文档</Title>
              <Text type="secondary">知识库的所有文件都在这里显示，上传完成后即可被助手检索和引用。</Text>
            </div>
            <Space>
              <Button icon={<BarChartOutlined />} onClick={openStats}>
                统计
              </Button>
              <Button icon={<UploadOutlined />} onClick={() => startUpload()} type="primary">
                添加文件
              </Button>
            </Space>
          </div>

          <div className="knowledge-toolbar">
            <Select
              className="knowledge-filter"
              options={[
                { value: "all", label: "全部" },
                { value: ".pdf", label: "PDF" },
                { value: ".txt", label: "TXT" },
                { value: ".md", label: "Markdown" }
              ]}
              value={documentFilter}
              onChange={setDocumentFilter}
            />
            <Input
              allowClear
              className="knowledge-search"
              placeholder="搜索"
              value={documentSearch}
              onChange={(event) => setDocumentSearch(event.target.value)}
            />
            <Select
              className="knowledge-sort"
              options={[
                { value: "uploaded_desc", label: "排序：上传时间" },
                { value: "name_asc", label: "排序：名称" },
                { value: "chunks_desc", label: "排序：片段数" }
              ]}
              value={documentSort}
              onChange={setDocumentSort}
            />
          </div>

          <Table<DocumentInfo>
            className="knowledge-table"
            dataSource={visibleDocuments}
            loading={loadingDocuments}
            locale={{ emptyText: <Empty description="还没有文档" /> }}
            pagination={false}
            rowKey="doc_id"
            onRow={(record) => ({
              onClick: () => openDocumentChunks(record)
            })}
            size="middle"
            columns={[
              {
                title: "#",
                width: 54,
                render: (_value: unknown, _record: DocumentInfo, index: number) => index + 1
              },
              {
                title: "名称",
                dataIndex: "filename",
                render: (_value: unknown, doc: DocumentInfo) => (
                  <Space>
                    <span className="document-file-icon">{documentExt(doc.filename || doc.doc_id)}</span>
                    <Text strong>{doc.filename || doc.doc_id}</Text>
                  </Space>
                )
              },
              {
                title: "分段模式",
                width: 140,
                render: (_value: unknown, doc: DocumentInfo) => {
                  const labels: Record<string, string> = { fixed: "固定长度", structure: "结构感知", recursive: "递归拆分" };
                  return <Tag>{labels[doc.strategy || "fixed"] || doc.strategy || "固定长度"}</Tag>;
                }
              },
              {
                title: "召回次数",
                width: 120,
                render: (_value: unknown, doc: DocumentInfo) => <Text>{doc.chunk_count || 0}</Text>
              },
              {
                title: "上传时间",
                dataIndex: "uploaded_at",
                width: 180,
                render: (value: string | undefined) => formatDate(value)
              },
              {
                title: "状态",
                width: 120,
                render: () => <Tag color="success">可用</Tag>
              },
              {
                title: "操作",
                width: 160,
                render: (_value: unknown, doc: DocumentInfo) => (
                  <Space size={4} onClick={(event) => event.stopPropagation()}>
                    <Button
                      icon={<EyeOutlined />}
                      size="small"
                      type="link"
                      onClick={(event) => {
                        event.stopPropagation();
                        openDocumentChunks(doc);
                      }}
                    >
                      分块
                    </Button>
                    <Button
                      size="small"
                      type="link"
                      onClick={(event) => {
                        event.stopPropagation();
                        startUpload(doc);
                      }}
                    >
                      更新
                    </Button>
                    <Popconfirm
                      cancelText="取消"
                      okButtonProps={{ danger: true }}
                      okText="删除"
                      onCancel={(event) => event?.stopPropagation()}
                      onConfirm={(event) => {
                        event?.stopPropagation();
                        void onDeleteDocument(doc);
                        if (selectedDoc?.doc_id === doc.doc_id) {
                          backToList();
                        }
                      }}
                      title={`确认删除“${doc.filename || doc.doc_id}”？`}
                      description="会同时删除文档记录、分块和向量索引。"
                    >
                      <Button danger size="small" type="link" onClick={(event) => event.stopPropagation()}>
                        删除
                      </Button>
                    </Popconfirm>
                  </Space>
                )
              }
            ]}
          />
        </main>
      ) : mode === "chunks" ? (
        <main className="document-chunks-page">
          <div className="document-chunks-page-head">
            <div>
              <Title level={4}>{selectedDoc?.filename || "文档分块"}</Title>
              <Text type="secondary">
                {loadingChunks ? "正在读取分块" : `${chunks.length} 个片段，点击片段查看完整内容`}
              </Text>
            </div>
            <Space>
              <Button
                icon={<ReloadOutlined />}
                loading={loadingChunks}
                onClick={() => setChunksReloadKey((value) => value + 1)}
              >
                刷新分块
              </Button>
              {selectedDoc && (
                <Button onClick={() => startUpload(selectedDoc)}>
                  更新文档
                </Button>
              )}
            </Space>
          </div>
          <List
            className="chunk-list chunk-page-list"
            dataSource={chunks}
            loading={loadingChunks}
            locale={{ emptyText: <Empty description="该文档暂无分块" /> }}
            renderItem={(chunk) => (
              <List.Item className="chunk-list-item chunk-page-item" onClick={() => setActiveChunk(chunk)}>
                <List.Item.Meta
                  title={
                    <Space wrap>
                      <Tag color="blue">片段 {String(chunk.metadata.chunk_index ?? chunk.chunk_id.slice(-6))}</Tag>
                      <Text strong>{chunk.length} 字</Text>
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
          <Drawer
            className="chunk-drawer"
            destroyOnClose
            onClose={() => setActiveChunk(null)}
            open={!!activeChunk}
            placement="right"
            title="分块详情"
            width={520}
          >
            {activeChunk && (
              <div className="chunk-detail">
                <Descriptions bordered column={1} size="small">
                  <Descriptions.Item label="文档">{selectedDoc?.filename}</Descriptions.Item>
                  <Descriptions.Item label="片段序号">
                    {String(activeChunk.metadata.chunk_index ?? "无")}
                  </Descriptions.Item>
                  <Descriptions.Item label="页码">{String(activeChunk.metadata.page ?? "无")}</Descriptions.Item>
                  <Descriptions.Item label="标题路径">
                    {Array.isArray(activeChunk.metadata.heading_path) && (activeChunk.metadata.heading_path as string[]).length > 0
                      ? (activeChunk.metadata.heading_path as string[]).join(" > ")
                      : "无"}
                  </Descriptions.Item>
                  <Descriptions.Item label="长度">{activeChunk.length} 字</Descriptions.Item>
                </Descriptions>
                <pre>{activeChunk.text}</pre>
              </div>
            )}
          </Drawer>
        </main>
      ) : (

        <main className="ingest-panel">
          <Steps
            current={step}
            items={[
              { title: "选择文档" },
              { title: "文档信息" },
              { title: "清洗配置" },
              { title: "分块配置" },
              { title: "确认入库" }
            ]}
          />

          <section className="ingest-section">
            {step === 0 && !stage && (
              <Upload.Dragger
                accept=".txt,.pdf,.md"
                disabled={stagingDocument}
                customRequest={({ file, onError, onSuccess }: UploadRequestOption) => {
                  handleStageFile(file as File)
                    .then((data) => onSuccess?.(data))
                    .catch((error) => onError?.(error));
                }}
                maxCount={1}
                showUploadList={false}
              >
                <p className="upload-icon">
                  <UploadOutlined />
                </p>
                <p className="upload-title">{stagingDocument ? "正在解析文档" : "选择要入库的文档"}</p>
                <p className="upload-hint">支持 txt、pdf、md。上传后先预览，不会立即写入知识库。</p>
              </Upload.Dragger>
            )}

            {step === 1 && stage && metadata && (
              <div className="ingest-grid ingest-grid-single">
                <section className="ingest-card">
                  <div className="ingest-card-header">
                    <Text strong>文档信息</Text>
                    <Button size="small" onClick={resetStage}>
                      重新选择
                    </Button>
                  </div>
                  <Descriptions column={2} size="small">
                    <Descriptions.Item label="文件">{stage.filename}</Descriptions.Item>
                    <Descriptions.Item label="类型">{stage.file_type}</Descriptions.Item>
                    <Descriptions.Item label="页/段">{stage.page_count}</Descriptions.Item>
                    <Descriptions.Item label="大小">{formatFileSize(stage.file_size)}</Descriptions.Item>
                  </Descriptions>
                  <div className="metadata-form">
                    <label>
                      <Text type="secondary">文档名称</Text>
                      <Input
                        value={metadata.title}
                        onChange={(event) => setMetadata({ ...metadata, title: event.target.value })}
                      />
                    </label>
                    <label>
                      <Text type="secondary">文档类型</Text>
                      <Select
                        value={metadata.category}
                        options={[
                          { value: "policy", label: "政策文件" },
                          { value: "guide", label: "办事指南" },
                          { value: "faq", label: "常见问答" },
                          { value: "notice", label: "通知公告" },
                          { value: "other", label: "其他" }
                        ]}
                        onChange={(value) => setMetadata({ ...metadata, category: value })}
                      />
                    </label>
                    <label>
                      <Text type="secondary">发布机构</Text>
                      <Input
                        value={metadata.organization || ""}
                        onChange={(event) => setMetadata({ ...metadata, organization: event.target.value })}
                      />
                    </label>
                    <label>
                      <Text type="secondary">适用地区</Text>
                      <Input
                        value={metadata.region || ""}
                        onChange={(event) => setMetadata({ ...metadata, region: event.target.value })}
                      />
                    </label>
                    <label>
                      <Text type="secondary">发布时间</Text>
                      <Input
                        placeholder="例如 2024-06-01"
                        value={metadata.publish_date || ""}
                        onChange={(event) => setMetadata({ ...metadata, publish_date: event.target.value })}
                      />
                    </label>
                    <label>
                      <Text type="secondary">关键词</Text>
                      <Input
                        placeholder="用逗号分隔"
                        value={metadata.keywords.join(",")}
                        onChange={(event) =>
                          setMetadata({
                            ...metadata,
                            keywords: event.target.value
                              .split(/[,，]/)
                              .map((item) => item.trim())
                              .filter(Boolean)
                          })
                        }
                      />
                    </label>
                    <label className="metadata-wide">
                      <Text type="secondary">备注</Text>
                      <Input.TextArea
                        rows={2}
                        value={metadata.notes || ""}
                        onChange={(event) => setMetadata({ ...metadata, notes: event.target.value })}
                      />
                    </label>
                  </div>
                </section>
              </div>
            )}

            {step === 2 && stage && cleanOptions && (
              <div className="ingest-grid">
                <section className="ingest-card">
                  <div className="ingest-card-header">
                    <Text strong>清洗配置</Text>
                  </div>
                  <div className="option-grid">
                    <Checkbox
                      checked={cleanOptions.trim_lines}
                      onChange={(event) => setCleanOptions({ ...cleanOptions, trim_lines: event.target.checked })}
                    >
                      去除行首尾空格
                    </Checkbox>
                    <Checkbox
                      checked={cleanOptions.normalize_spaces}
                      onChange={(event) => setCleanOptions({ ...cleanOptions, normalize_spaces: event.target.checked })}
                    >
                      合并多余空格
                    </Checkbox>
                    <Checkbox
                      checked={cleanOptions.merge_blank_lines}
                      onChange={(event) => setCleanOptions({ ...cleanOptions, merge_blank_lines: event.target.checked })}
                    >
                      合并连续空行
                    </Checkbox>
                    <Checkbox
                      checked={cleanOptions.merge_broken_lines}
                      onChange={(event) => setCleanOptions({ ...cleanOptions, merge_broken_lines: event.target.checked })}
                    >
                      合并断行
                    </Checkbox>
                  </div>
                  <Button loading={previewing} onClick={handlePreview} type="primary" style={{ marginTop: 8 }}>
                    刷新预览
                  </Button>
                </section>

                <section className="ingest-card preview-card">
                  <div className="ingest-card-header">
                    <Text strong>清洗预览</Text>
                  </div>
                  <div className="preview-columns">
                    <div>
                      <Text type="secondary">原文片段</Text>
                      <pre>{stage.raw_preview || "暂无内容"}</pre>
                    </div>
                    <div>
                      <Text type="secondary">清洗后</Text>
                      <pre>{stage.cleaned_preview || "暂无内容"}</pre>
                    </div>
                  </div>
                </section>
              </div>
            )}

            {step === 3 && stage && splitOptions && (
              <div className="ingest-grid">
                <section className="ingest-card">
                  <div className="ingest-card-header">
                    <Text strong>分块配置</Text>
                  </div>
                  <label style={{ display: "grid", gap: 6 }}>
                    <Text type="secondary">分块策略</Text>
                    <Select
                      value={splitOptions.strategy}
                      options={[
                        { value: "fixed", label: "固定长度 - 按字符数等距切分" },
                        { value: "structure", label: "结构感知 - 按文档标题层级切分" },
                        { value: "recursive", label: "递归分块 - 按分隔符逐级下钻" }
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
                  <div className="split-controls">
                    <label>
                      <Text type="secondary">片段长度</Text>
                      <InputNumber
                        min={50}
                        max={3000}
                        value={splitOptions.chunk_size}
                        onChange={(value) => setSplitOptions({ ...splitOptions, chunk_size: Number(value || 500) })}
                      />
                    </label>
                    <label>
                      <Text type="secondary">
                        重叠长度
                        {splitOptions.strategy === "structure" && (
                          <Text type="secondary" style={{ fontSize: 12 }}>（建议为 0）</Text>
                        )}
                      </Text>
                      <InputNumber
                        min={0}
                        max={1000}
                        value={splitOptions.chunk_overlap}
                        onChange={(value) => setSplitOptions({ ...splitOptions, chunk_overlap: Number(value || 0) })}
                      />
                    </label>
                  </div>
                  {splitOptions.strategy === "recursive" && (
                    <label style={{ display: "grid", gap: 6 }}>
                      <Text type="secondary">分隔符预设</Text>
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
                  <Checkbox
                    checked={splitOptions.attach_title}
                    onChange={(event) => setSplitOptions({ ...splitOptions, attach_title: event.target.checked })}
                  >
                    每个片段附带文档标题
                  </Checkbox>
                  <Button loading={previewing} onClick={handlePreview} type="primary" style={{ marginTop: 8 }}>
                    刷新预览
                  </Button>
                </section>

                <section className="ingest-card preview-card">
                  <div className="ingest-card-header">
                    <Text strong>分块预览</Text>
                    <Tag>{stage.chunk_count} 个片段</Tag>
                  </div>
                  <div className="chunk-preview-list">
                    {stage.chunk_preview.map((chunk) => (
                      <article className="chunk-preview" key={chunk.index}>
                        <Space wrap>
                          <Tag>#{chunk.index}</Tag>
                          <Text type="secondary">{chunk.length} 字</Text>
                          {chunk.page !== undefined && chunk.page !== null && (
                            <Text type="secondary">页码 {chunk.page}</Text>
                          )}
                          {chunk.heading_path && chunk.heading_path.length > 0 && (
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              {Array.isArray(chunk.heading_path) ? (chunk.heading_path as string[]).join(" > ") : String(chunk.heading_path)}
                            </Text>
                          )}
                        </Space>
                        <p>{chunk.text}</p>
                      </article>
                    ))}
                  </div>
                </section>
              </div>
            )}

            {step === 4 && stage && metadata && cleanOptions && splitOptions && (
              <div className="ingest-grid ingest-grid-single">
                <section className="ingest-card">
                  <div className="ingest-card-header">
                    <Text strong>确认入库</Text>
                    <Tag>{stage.chunk_count} 个片段</Tag>
                  </div>
                  <Descriptions bordered column={1} size="small">
                    <Descriptions.Item label="文件">{stage.filename}（{stage.file_type.toUpperCase()} / {formatFileSize(stage.file_size)}）</Descriptions.Item>
                    <Descriptions.Item label="文档名称">{metadata.title}</Descriptions.Item>
                    <Descriptions.Item label="文档类型">{
                      { policy: "政策文件", guide: "办事指南", faq: "常见问答", notice: "通知公告", other: "其他" }[metadata.category] || metadata.category
                    }</Descriptions.Item>
                    {metadata.organization && <Descriptions.Item label="发布机构">{metadata.organization}</Descriptions.Item>}
                    {metadata.region && <Descriptions.Item label="适用地区">{metadata.region}</Descriptions.Item>}
                    {metadata.publish_date && <Descriptions.Item label="发布时间">{metadata.publish_date}</Descriptions.Item>}
                    {metadata.keywords.length > 0 && <Descriptions.Item label="关键词">{metadata.keywords.join("、")}</Descriptions.Item>}
                    <Descriptions.Item label="清洗策略">
                      {[
                        cleanOptions.trim_lines && "去除行首尾空格",
                        cleanOptions.normalize_spaces && "合并多余空格",
                        cleanOptions.merge_blank_lines && "合并连续空行",
                        cleanOptions.merge_broken_lines && "合并断行"
                      ].filter(Boolean).join("、") || "无"}
                    </Descriptions.Item>
                    <Descriptions.Item label="分块策略">
                      {{
                        fixed: "固定长度",
                        structure: "结构感知",
                        recursive: "递归分块"
                      }[splitOptions.strategy]} / 片段 {splitOptions.chunk_size} 字
                      {splitOptions.strategy !== "structure" && ` / 重叠 ${splitOptions.chunk_overlap} 字`}
                      {splitOptions.strategy === "recursive" && ` / ${splitOptions.separator_preset === "chinese" ? "中文优先" : splitOptions.separator_preset === "english" ? "英文优先" : "通用分隔符"}`}
                      {splitOptions.attach_title && " / 附带标题"}
                    </Descriptions.Item>
                  </Descriptions>
                  <div style={{ marginTop: 12 }}>
                    <Button disabled={!stage.chunk_count} loading={committing} onClick={handleCommit} type="primary" block>
                      {replaceDoc ? "确认更新" : "确认入库"}
                    </Button>
                  </div>
                </section>
              </div>
            )}
          </section>
          {step > 0 && step < 4 && (
            <div className="ingest-step-footer">
              <Button onClick={() => setStep((value) => Math.max(value - 1, 0))}>
                上一步
              </Button>
              <Button type="primary" loading={previewing} onClick={() => goNext(step + 1)}>
                下一步
              </Button>
            </div>
          )}
          {step === 4 && (
            <div className="ingest-step-footer">
              <Button onClick={() => setStep(3)}>
                上一步
              </Button>
            </div>
          )}
        </main>
      )}

      <Modal
        footer={null}
        loading={loadingStats}
        onCancel={() => setStatsOpen(false)}
        open={statsOpen}
        title="知识库统计总览"
        width={560}
      >
        {stats && (
          <Row gutter={[16, 16]}>
            <Col span={8}>
              <Card size="small">
                <Statistic title="文档数量" value={stats.document_count} suffix="个" />
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small">
                <Statistic title="片段总数" value={stats.total_chunks} suffix="个" />
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small">
                <Statistic title="总文本量" value={stats.total_text_length} suffix="字" />
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small">
                <Statistic title="最大文本" value={stats.max_text_length} suffix="字" />
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small">
                <Statistic title="最小文本" value={stats.min_text_length} suffix="字" />
              </Card>
            </Col>
          </Row>
        )}
        {stats && Object.keys(stats.format_distribution).length > 0 && (
          <div style={{ marginTop: 20 }}>
            <Text strong style={{ display: "block", marginBottom: 8 }}>格式分布</Text>
            <Table
              columns={[
                { title: "格式", dataIndex: "format", render: (value: string) => <Tag>{value.toUpperCase()}</Tag> },
                { title: "数量", dataIndex: "count" }
              ]}
              dataSource={Object.entries(stats.format_distribution).map(([format, count]) => ({ format, count, key: format }))}
              pagination={false}
              size="small"
            />
          </div>
        )}
      </Modal>
    </section>
  );
}
