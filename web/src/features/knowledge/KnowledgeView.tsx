import { ArrowLeftOutlined, CheckCircleOutlined, EyeOutlined, ReloadOutlined, UploadOutlined } from "@ant-design/icons";
import { App, Button, Checkbox, Descriptions, Drawer, Empty, Input, InputNumber, List, Popconfirm, Select, Space, Steps, Table, Tag, Typography, Upload } from "antd";
import type { UploadRequestOption } from "rc-upload/lib/interface";
import { useEffect, useState } from "react";
import { commitDocumentStage, listDocumentChunks, previewDocumentStage, stageDocument } from "../../api";
import type { CleanOptions, DocumentChunk, DocumentInfo, DocumentMetadataInput, DocumentStage, SplitOptions } from "../../types";
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
      message.success({ content: "文档已解析，请补充信息并确认预览", key: "stage-document" });
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
      setStep(2);
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
      setStep(3);
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
                render: () => <Tag>通用</Tag>
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
              { title: "补充信息" },
              { title: "预览确认" },
              { title: "入库完成" }
            ]}
          />

          <section className="ingest-section">
            {!stage ? (
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
            ) : (
              <div className="ingest-grid">
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
                  {metadata && (
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
                  )}
                </section>

                <section className="ingest-card">
                  <Text strong>清洗与分块</Text>
                  {cleanOptions && (
                    <div className="option-grid">
                      <Checkbox
                        checked={cleanOptions.trim_lines}
                        onChange={(event) => setCleanOptions({ ...cleanOptions, trim_lines: event.target.checked })}
                      >
                        去除行首尾空格
                      </Checkbox>
                      <Checkbox
                        checked={cleanOptions.normalize_spaces}
                        onChange={(event) =>
                          setCleanOptions({ ...cleanOptions, normalize_spaces: event.target.checked })
                        }
                      >
                        合并多余空格
                      </Checkbox>
                      <Checkbox
                        checked={cleanOptions.merge_blank_lines}
                        onChange={(event) =>
                          setCleanOptions({ ...cleanOptions, merge_blank_lines: event.target.checked })
                        }
                      >
                        合并连续空行
                      </Checkbox>
                      <Checkbox
                        checked={cleanOptions.merge_broken_lines}
                        onChange={(event) =>
                          setCleanOptions({ ...cleanOptions, merge_broken_lines: event.target.checked })
                        }
                      >
                        合并断行
                      </Checkbox>
                    </div>
                  )}
                  {splitOptions && (
                    <div className="split-controls">
                      <label>
                        <Text type="secondary">片段长度</Text>
                        <InputNumber
                          min={50}
                          max={3000}
                          value={splitOptions.chunk_size}
                          onChange={(value) =>
                            setSplitOptions({ ...splitOptions, chunk_size: Number(value || 500) })
                          }
                        />
                      </label>
                      <label>
                        <Text type="secondary">重叠长度</Text>
                        <InputNumber
                          min={0}
                          max={1000}
                          value={splitOptions.chunk_overlap}
                          onChange={(value) =>
                            setSplitOptions({ ...splitOptions, chunk_overlap: Number(value || 0) })
                          }
                        />
                      </label>
                      <Checkbox
                        checked={splitOptions.attach_title}
                        onChange={(event) =>
                          setSplitOptions({ ...splitOptions, attach_title: event.target.checked })
                        }
                      >
                        每个片段附带文档标题
                      </Checkbox>
                    </div>
                  )}
                  <Space>
                    <Button loading={previewing} onClick={handlePreview} type="primary">
                      重新生成预览
                    </Button>
                    <Button disabled={!stage.chunk_count} loading={committing} onClick={handleCommit}>
                      {replaceDoc ? "确认更新" : "确认入库"}
                    </Button>
                  </Space>
                </section>

                <section className="ingest-card preview-card">
                  <div className="ingest-card-header">
                    <Text strong>清洗预览</Text>
                    <Tag>{stage.chunk_count} 个片段</Tag>
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

                <section className="ingest-card preview-card">
                  <div className="ingest-card-header">
                    <Text strong>分块预览</Text>
                    {step === 3 && (
                      <Tag color="success" icon={<CheckCircleOutlined />}>
                        已入库
                      </Tag>
                    )}
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
                        </Space>
                        <p>{chunk.text}</p>
                      </article>
                    ))}
                  </div>
                </section>
              </div>
            )}
          </section>
        </main>
      )}
    </section>
  );
}
