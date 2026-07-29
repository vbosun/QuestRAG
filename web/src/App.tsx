import {
  ArrowsAltOutlined,
  BarChartOutlined,
  BookOutlined,
  CheckCircleOutlined,
  ArrowLeftOutlined,
  CopyOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  FileTextOutlined,
  MessageOutlined,
  PlusOutlined,
  ReloadOutlined,
  SendOutlined,
  ShrinkOutlined,
  UploadOutlined
} from "@ant-design/icons";
import {
  App,
  Avatar,
  Button,
  Checkbox,
  ConfigProvider,
  Descriptions,
  Drawer,
  Empty,
  Input,
  InputNumber,
  Layout,
  List,
  Menu,
  Popconfirm,
  Select,
  Space,
  Steps,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload
} from "antd";
import type { UploadRequestOption } from "rc-upload/lib/interface";
import React, { useEffect, useMemo, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  commitDocumentStage,
  deleteDocument,
  listDocuments,
  listDocumentChunks,
  previewDocumentStage,
  stageDocument,
  streamChat,
  uploadDocument
} from "./api";
import { parseMessageParts } from "./artifacts";
import { downloadText, messagePartsToMarkdown } from "./download";
import type {
  Artifact,
  ChartArtifact,
  ChatMessage,
  CitationSource,
  CleanOptions,
  DocumentChunk,
  DocumentInfo,
  DocumentMetadataInput,
  DocumentStage,
  MessagePart,
  Session,
  SplitOptions
} from "./types";

const STORAGE_KEY = "questrag.chat.sessions.v2";
const { Content, Sider } = Layout;
const { Text, Title } = Typography;

export function QuestRagApp() {
  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: "#245b61",
          colorInfo: "#245b61",
          colorSuccess: "#28705f",
          colorWarning: "#b76f18",
          colorError: "#b84242",
          borderRadius: 8,
          fontFamily:
            'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif'
        }
      }}
    >
      <App>
        <Workspace />
      </App>
    </ConfigProvider>
  );
}

function Workspace() {
  const { message } = App.useApp();
  const [activeMenu, setActiveMenu] = useState("chat");
  const [sessions, setSessions] = useState<Session[]>(() => loadSessions());
  const [activeSessionId, setActiveSessionId] = useState(() => loadSessions()[0]?.id);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [documentError, setDocumentError] = useState("");
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) || sessions[0],
    [activeSessionId, sessions]
  );

  useEffect(() => {
    if (!sessions.length) {
      const session = createBlankSession();
      setSessions([session]);
      setActiveSessionId(session.id);
    }
  }, [sessions.length]);

  useEffect(() => {
    saveSessions(sessions);
  }, [sessions]);

  useEffect(() => {
    void refreshDocuments();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: "end" });
  }, [activeSession?.messages.length, sending]);

  function updateSession(sessionId: string, updater: (session: Session) => Session) {
    setSessions((current) =>
      current.map((session) => (session.id === sessionId ? updater({ ...session }) : session))
    );
  }

  function createSession() {
    const session = createBlankSession();
    setSessions((current) => [session, ...current]);
    setActiveSessionId(session.id);
    setActiveMenu("chat");
  }

  function removeSession(id: string) {
    setSessions((current) => {
      if (current.length <= 1) {
        const next = createBlankSession();
        setActiveSessionId(next.id);
        return [next];
      }
      const next = current.filter((session) => session.id !== id);
      if (activeSessionId === id) setActiveSessionId(next[0]?.id);
      return next;
    });
  }

  async function refreshDocuments() {
    setLoadingDocuments(true);
    setDocumentError("");
    try {
      setDocuments(await listDocuments());
    } catch (error) {
      setDocuments([]);
      setDocumentError(error instanceof Error ? error.message : "读取文档失败");
    } finally {
      setLoadingDocuments(false);
    }
  }

  async function handleUpload(file: File) {
    const result = await uploadDocument(file);
    const session = activeSession;
    if (session) {
      updateSession(session.id, (draft) => ({
        ...draft,
        uploads: [
          {
            filename: file.name,
            chunkCount: result.chunk_count,
            uploadedAt: new Date().toISOString()
          },
          ...draft.uploads
        ],
        updatedAt: new Date().toISOString()
      }));
    }
    message.success(`${file.name} 上传完成，已索引 ${result.chunk_count} 个片段`);
    await refreshDocuments();
  }

  async function handleDeleteDocument(doc: DocumentInfo) {
    await deleteDocument(doc.doc_id);
    message.success(`${doc.filename || doc.doc_id} 已删除`);
    await refreshDocuments();
  }

  async function sendMessage() {
    const text = inputValue.trim();
    const session = activeSession;
    if (!text || !session || sending) return;

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text
    };
    const assistantId = crypto.randomUUID();
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: "assistant",
      raw: "",
      parts: [{ type: "markdown", content: "" }],
      status: "正在准备回答..."
    };
    const nextMessages = [...session.messages, userMessage, assistantMessage];

    setInputValue("");
    setSending(true);
    updateSession(session.id, (draft) => ({
      ...draft,
      title: draft.title === "新会话" ? text.slice(0, 24) : draft.title,
      messages: nextMessages,
      updatedAt: new Date().toISOString()
    }));

    try {
      await streamChat(
        {
          message: text,
          session_id: session.id,
          history: nextMessages
        },
        (event) => {
          if (event.event === "meta") {
            setActiveSessionId(event.data.session_id);
            return;
          }

          if (event.event === "delta") {
            updateAssistantMessage(session.id, assistantId, (current) => {
              const raw = `${current.raw || ""}${event.data.text}`;
              return {
                ...current,
                raw,
                parts: parseMessageParts(raw),
                status: undefined
              };
            });
            return;
          }

          if (event.event === "status") {
            updateAssistantMessage(session.id, assistantId, (current) => ({
              ...current,
              status: event.data.message
            }));
            return;
          }

          if (event.event === "artifact") {
            updateAssistantMessage(session.id, assistantId, (current) => ({
              ...current,
              parts: [...(current.parts || []), artifactToPart(event.data)]
            }));
            return;
          }

          if (event.event === "sources") {
            updateAssistantMessage(session.id, assistantId, (current) => ({
              ...current,
              citations: event.data.sources
            }));
            return;
          }

          if (event.event === "done") {
            updateAssistantMessage(session.id, assistantId, (current) => ({
              ...current,
              status: undefined
            }));
            return;
          }

          if (event.event === "error") {
            updateAssistantMessage(session.id, assistantId, (current) => ({
              ...current,
              error: true,
              parts: [
                ...(current.parts || []),
                { type: "markdown", content: `\n\n请求失败：${event.data.message}` }
              ]
            }));
          }
        }
      );
    } catch (error) {
      updateAssistantMessage(session.id, assistantId, (current) => ({
        ...current,
        error: true,
        parts: [
          {
            type: "markdown",
            content: `请求失败：${error instanceof Error ? error.message : "请稍后重试"}`
          }
        ]
      }));
    } finally {
      setSending(false);
    }
  }

  function updateAssistantMessage(
    sessionId: string,
    messageId: string,
    updater: (message: ChatMessage) => ChatMessage
  ) {
    updateSession(sessionId, (draft) => ({
      ...draft,
      messages: draft.messages.map((item) => (item.id === messageId ? updater(item) : item)),
      updatedAt: new Date().toISOString()
    }));
  }

  return (
    <Layout className="app-shell">
      <Sider className="app-sider" breakpoint="lg" collapsedWidth={0} width={232}>
        <div className="brand">
          <div className="brand-mark">Q</div>
          <div>
            <Title level={4}>QuestRAG</Title>
            <Text type="secondary">知识库问答工作台</Text>
          </div>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[activeMenu]}
          items={[
            { key: "chat", icon: <MessageOutlined />, label: "助手聊天" },
            { key: "knowledge", icon: <BookOutlined />, label: "知识库管理" }
          ]}
          onClick={({ key }) => setActiveMenu(key)}
        />
        <div className="sider-summary">
          <Text type="secondary">{documents.length} 个文档</Text>
          <Text type="secondary">{sessions.length} 个会话</Text>
        </div>
      </Sider>
      <Content className="app-content">
        {activeMenu === "chat" ? (
          <ChatView
            activeSession={activeSession}
            documents={documents}
            inputValue={inputValue}
            messagesEndRef={messagesEndRef}
            onCreateSession={createSession}
            onDeleteSession={removeSession}
            onInputChange={setInputValue}
            onSelectSession={setActiveSessionId}
            onSendMessage={sendMessage}
            sending={sending}
            sessions={sessions}
          />
        ) : (
          <KnowledgeView
            documents={documents}
            documentError={documentError}
            loadingDocuments={loadingDocuments}
            onDeleteDocument={handleDeleteDocument}
            onRefreshDocuments={refreshDocuments}
          />
        )}
      </Content>
    </Layout>
  );
}

interface ChatViewProps {
  activeSession?: Session;
  documents: DocumentInfo[];
  inputValue: string;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  onCreateSession: () => void;
  onDeleteSession: (id: string) => void;
  onInputChange: (value: string) => void;
  onSelectSession: (id: string) => void;
  onSendMessage: () => void;
  sending: boolean;
  sessions: Session[];
}

function ChatView(props: ChatViewProps) {
  const messages = props.activeSession?.messages || [];
  return (
    <section className="view-shell chat-view">
      <aside className="session-panel">
        <Space className="section-title" direction="vertical" size={2}>
          <Text strong>会话</Text>
          <Text type="secondary">切换上下文记录</Text>
        </Space>
        <Button block icon={<PlusOutlined />} type="primary" onClick={props.onCreateSession}>
          新会话
        </Button>
        <SessionList
          activeSessionId={props.activeSession?.id}
          onDeleteSession={props.onDeleteSession}
          onSelectSession={props.onSelectSession}
          sessions={props.sessions}
        />
      </aside>
      <main className="chat-panel">
        <header className="panel-header">
          <div>
            <Title level={3}>{props.activeSession?.title || "新会话"}</Title>
            <Text type="secondary">
              {props.documents.length
                ? `已接入 ${props.documents.length} 个知识库文档`
                : "上传文档后，可以直接围绕资料提问"}
            </Text>
          </div>
        </header>
        <div className="messages" aria-live="polite">
          {messages.length ? (
            messages.map((item) => <ChatBubble key={item.id} message={item} />)
          ) : (
            <Empty className="chat-empty" description="这里会显示当前会话的问答记录" />
          )}
          <div ref={props.messagesEndRef} />
        </div>
        <footer className="composer">
          <textarea
            disabled={props.sending}
            onChange={(event) => props.onInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void props.onSendMessage();
              }
            }}
            placeholder="输入问题，按 Enter 发送，Shift + Enter 换行"
            rows={1}
            value={props.inputValue}
          />
          <Button
            disabled={!props.inputValue.trim()}
            icon={<SendOutlined />}
            loading={props.sending}
            onClick={props.onSendMessage}
            type="primary"
          >
            发送
          </Button>
        </footer>
      </main>
    </section>
  );
}

function SessionList({
  activeSessionId,
  onDeleteSession,
  onSelectSession,
  sessions
}: {
  activeSessionId?: string;
  onDeleteSession: (id: string) => void;
  onSelectSession: (id: string) => void;
  sessions: Session[];
}) {
  return (
    <List
      className="session-list"
      dataSource={sessions}
      locale={{ emptyText: "暂无会话" }}
      renderItem={(session) => (
        <List.Item
          className={session.id === activeSessionId ? "session-item active" : "session-item"}
          onClick={() => onSelectSession(session.id)}
        >
          <div className="session-info">
            <Text strong ellipsis>
              {session.title}
            </Text>
            <Text type="secondary">
              {session.messages.length ? `${session.messages.length} 条消息` : "尚未开始"}
            </Text>
          </div>
          <Popconfirm
            cancelText="取消"
            okButtonProps={{ danger: true }}
            okText="删除"
            onConfirm={(event) => {
              event?.stopPropagation();
              onDeleteSession(session.id);
            }}
            title="删除这个会话？"
          >
            <Button
              danger
              icon={<DeleteOutlined />}
              size="small"
              type="text"
              onClick={(event) => event.stopPropagation()}
            />
          </Popconfirm>
        </List.Item>
      )}
    />
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const [expanded, setExpanded] = useState(false);
  const [activeCitation, setActiveCitation] = useState<CitationSource | null>(null);
  const isUser = message.role === "user";
  const hasAssistantContent = Boolean((message.raw || "").trim() || message.parts?.some((part) => {
    if (part.type === "markdown") return Boolean(part.content.trim());
    return true;
  }));
  const parts = isUser
    ? [{ type: "markdown", content: message.content || "" } as MessagePart]
    : message.parts || [{ type: "markdown", content: message.raw || "" }];
  const markdown = messagePartsToMarkdown(parts);

  return (
    <article className={`message-row ${isUser ? "user" : "assistant"}`}>
      {!isUser && <Avatar className="message-avatar">AI</Avatar>}
      <div
        className={`message-bubble ${isUser ? "user-bubble" : "assistant-bubble"}${
          message.error ? " error-bubble" : ""
        } ${expanded ? "expanded" : "collapsed"}`}
      >
        <div className="message-content">
          {!isUser && message.status && (
            <div className="message-status">
              <span className="status-dot" />
              <Text type="secondary">{message.status}</Text>
            </div>
          )}
          {parts.map((part, index) => (
            <MessagePartView
              citations={message.citations || []}
              key={`${message.id}-${index}`}
              onSelectCitation={setActiveCitation}
              part={part}
            />
          ))}
          {!isUser && !!message.citations?.length && (
            <CitationList citations={message.citations} onSelectCitation={setActiveCitation} />
          )}
        </div>
        {!isUser && hasAssistantContent && (
          <Space className="message-actions" size={4} wrap>
            <Tooltip title={expanded ? "收起回答" : "展开回答"}>
              <Button
                aria-label={expanded ? "收起回答" : "展开回答"}
                icon={expanded ? <ShrinkOutlined /> : <ArrowsAltOutlined />}
                size="small"
                type="text"
                onClick={() => setExpanded((value) => !value)}
              />
            </Tooltip>
            <Tooltip title="复制回答">
              <Button
                aria-label="复制回答"
                icon={<CopyOutlined />}
                size="small"
                type="text"
                onClick={() => void navigator.clipboard.writeText(markdown)}
              />
            </Tooltip>
            <Tooltip title="下载回答">
              <Button
                aria-label="下载回答"
                icon={<DownloadOutlined />}
                size="small"
                type="text"
                onClick={() => downloadText("questrag-answer.md", markdown)}
              />
            </Tooltip>
          </Space>
        )}
      </div>
      {activeCitation && (
        <CitationDrawer citation={activeCitation} onClose={() => setActiveCitation(null)} />
      )}
      {isUser && <Avatar className="message-avatar user-avatar">你</Avatar>}
    </article>
  );
}

function MessagePartView({
  citations,
  onSelectCitation,
  part
}: {
  citations: CitationSource[];
  onSelectCitation: (citation: CitationSource) => void;
  part: MessagePart;
}) {
  if (part.type === "chart") return <ChartCard artifact={part.artifact} />;
  if (part.type === "report") return <ReportCard artifact={part.artifact} />;
  const citationMap = new Map(citations.map((citation) => [citation.label, citation]));
  return (
    <div className="markdown-body">
      <ReactMarkdown
        components={{
          a: ({ children, href }) => {
            const match = href?.match(/^citation:(.+)$/);
            if (match) {
              const citation = citationMap.get(decodeURIComponent(match[1]));
              return (
                <button
                  className={`citation-inline${citation ? "" : " missing"}`}
                  onClick={() => citation && onSelectCitation(citation)}
                  type="button"
                >
                  {children}
                </button>
              );
            }
            return (
              <a href={href} rel="noreferrer" target="_blank">
                {children}
              </a>
            );
          }
        }}
        remarkPlugins={[remarkGfm]}
        urlTransform={(url) =>
          url.startsWith("citation:") ? url : defaultUrlTransform(url)
        }
      >
        {citations.length ? formatCitationMarkdown(part.content || " ") : part.content || " "}
      </ReactMarkdown>
    </div>
  );
}

function formatCitationMarkdown(content: string) {
  const codeBlocks: string[] = [];
  const masked = content.replace(/```[\s\S]*?```/g, (block) => {
    const token = `@@CODE_BLOCK_${codeBlocks.length}@@`;
    codeBlocks.push(block);
    return token;
  });

  const linked = masked.replace(/【(\d{1,2})】/g, (_match, label: string) => {
    return `[${label}](citation:${encodeURIComponent(label)})`;
  });

  return codeBlocks.reduce(
    (current, block, index) => current.replace(`@@CODE_BLOCK_${index}@@`, block),
    linked
  );
}

function CitationList({
  citations,
  onSelectCitation
}: {
  citations: CitationSource[];
  onSelectCitation: (citation: CitationSource) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <section className="citation-list" aria-label="回答来源">
      <div className="citation-list-header">
        <Space size={8}>
          <Text strong>来源引用</Text>
          <Text type="secondary">{citations.length} 条</Text>
        </Space>
        <Button size="small" type="text" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "收起" : "查看"}
        </Button>
      </div>
      {expanded && (
        <div className="citation-items">
          {citations.map((citation) => (
            <button
              className="citation-item"
              key={`${citation.label}-${citation.ref_id}`}
              onClick={() => onSelectCitation(citation)}
              type="button"
            >
              <span className="citation-badge">[{citation.label}]</span>
              <span className="citation-title">{citation.title}</span>
              <Tag>{citation.source_type === "job" ? "岗位" : "知识库"}</Tag>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function CitationDrawer({
  citation,
  onClose
}: {
  citation: CitationSource;
  onClose: () => void;
}) {
  const metadata = citation.metadata || {};
  const rows =
    citation.source_type === "job"
      ? [
          ["来源", metadata.source],
          ["单位", metadata.company],
          ["地点", metadata.address],
          ["薪资", metadata.salary],
          ["学历", metadata.education],
          ["经验", metadata.experience]
        ]
      : [
          ["文档", citation.title],
          ["页码", metadata.page_label ?? metadata.page ?? "无"],
          ["片段", metadata.chunk_index ?? "无"]
        ];
  const visibleRows = rows.filter(([, value]) => value !== undefined && value !== null && value !== "");

  return (
    <Drawer
      className="citation-drawer"
      destroyOnClose
      onClose={onClose}
      open
      placement="right"
      title={
        <Space size={8}>
          <span className="citation-badge">[{citation.label}]</span>
          <span>{citation.source_type === "job" ? citation.title : "引用来源"}</span>
        </Space>
      }
      width={420}
    >
      <div className="citation-meta">
        {visibleRows.map(([label, value]) => (
          <div className="citation-meta-row" key={String(label)}>
            <Text type="secondary">{String(label)}</Text>
            <Text>{String(value)}</Text>
          </div>
        ))}
      </div>
      <div className="citation-snippet">{citation.snippet || "暂无片段预览"}</div>
    </Drawer>
  );
}

function ChartCard({ artifact }: { artifact: ChartArtifact }) {
  const chartRef = useRef<ReactECharts>(null);
  const option = buildChartOption(artifact);

  function downloadChart() {
    const instance = chartRef.current?.getEchartsInstance();
    const url = instance?.getDataURL({ pixelRatio: 2, backgroundColor: "#ffffff" });
    if (!url) return;
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = artifact.download?.filename || `${artifact.title}.png`;
    anchor.click();
  }

  return (
    <section className="artifact-card">
      <div className="artifact-header">
        <Space>
          <BarChartOutlined />
          <Text strong>{artifact.title}</Text>
          <Tag>{chartTypeLabel(artifact.chart_type)}</Tag>
        </Space>
        <Button icon={<DownloadOutlined />} size="small" onClick={downloadChart}>
          下载图表
        </Button>
      </div>
      {artifact.description && <Text type="secondary">{artifact.description}</Text>}
      <ReactECharts ref={chartRef} className="chart-canvas" option={option} notMerge />
      {artifact.source_note && <Text type="secondary">{artifact.source_note}</Text>}
    </section>
  );
}

function ReportCard({ artifact }: { artifact: Extract<MessagePart, { type: "report" }>["artifact"] }) {
  return (
    <section className="artifact-card">
      <div className="artifact-header">
        <Space>
          <FileTextOutlined />
          <Text strong>{artifact.title}</Text>
        </Space>
        <Button
          icon={<DownloadOutlined />}
          size="small"
          onClick={() => downloadText(artifact.download?.filename || `${artifact.title}.md`, artifact.content)}
        >
          下载报告
        </Button>
      </div>
      <div className="markdown-body report-body">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{artifact.content}</ReactMarkdown>
      </div>
    </section>
  );
}

function KnowledgeView({
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
    const result = await stageDocument(file);
    setStage(result);
    setMetadata(result.metadata);
    setCleanOptions(result.clean_options);
    setSplitOptions(result.split_options);
    setStep(1);
    message.success("文档已解析，请补充信息并确认预览");
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
              <Button>元数据</Button>
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
                  <Space size={4}>
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
                      onConfirm={() => onDeleteDocument(doc)}
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
                <p className="upload-title">选择要入库的文档</p>
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

function FileUploadButton({
  buttonText,
  onUploadFile
}: {
  buttonText: string;
  onUploadFile: (file: File) => Promise<void>;
}) {
  return (
    <Upload
      accept=".txt,.pdf,.md"
      customRequest={({ file, onError, onSuccess }: UploadRequestOption) => {
        onUploadFile(file as File)
          .then((data) => onSuccess?.(data))
          .catch((error) => onError?.(error));
      }}
      maxCount={1}
      showUploadList={false}
    >
      <Button icon={<UploadOutlined />} type="primary">
        {buttonText}
      </Button>
    </Upload>
  );
}

function artifactToPart(artifact: Artifact): MessagePart {
  if (artifact.type === "chart") return { type: "chart", artifact };
  return { type: "report", artifact };
}

function buildChartOption(artifact: ChartArtifact) {
  if (artifact.chart_type === "pie") {
    return {
      tooltip: { trigger: "item" },
      legend: { bottom: 0 },
      series: [
        {
          name: artifact.title,
          type: "pie",
          radius: ["38%", "68%"],
          data: artifact.data.map((item) => ({ name: item.name, value: item.value }))
        }
      ]
    };
  }

  const xAxis = Array.from(new Set(artifact.data.map((item) => item.name)));
  const groups = Array.from(new Set(artifact.data.map((item) => item.series || artifact.title)));
  const series = groups.map((group) => ({
    name: group,
    type: artifact.chart_type,
    smooth: artifact.chart_type === "line",
    data: xAxis.map((name) => {
      const item = artifact.data.find((entry) => entry.name === name && (entry.series || artifact.title) === group);
      return item?.value ?? 0;
    })
  }));

  return {
    tooltip: { trigger: "axis" },
    legend: { bottom: 0 },
    grid: { left: 36, right: 18, top: 28, bottom: 56 },
    xAxis: { type: "category", data: xAxis },
    yAxis: { type: "value" },
    series
  };
}

function chartTypeLabel(type: ChartArtifact["chart_type"]) {
  return { pie: "饼图", line: "折线图", bar: "柱状图" }[type];
}

function createBlankSession(): Session {
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    title: "新会话",
    messages: [],
    uploads: [],
    createdAt: now,
    updatedAt: now
  };
}

function loadSessions(): Session[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveSessions(sessions: Session[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

function formatDate(value?: string) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未知时间";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function formatFileSize(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function documentExt(value: string) {
  const ext = value.includes(".") ? value.split(".").pop()?.toUpperCase() : "DOC";
  return ext?.slice(0, 3) || "DOC";
}
