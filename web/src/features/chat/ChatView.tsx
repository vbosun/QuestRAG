import {
  ArrowsAltOutlined,
  BarChartOutlined,
  CopyOutlined,
  DeleteOutlined,
  DownloadOutlined,
  FileTextOutlined,
  PlusOutlined,
  SendOutlined,
  ShrinkOutlined
} from "@ant-design/icons";
import { Avatar, Breadcrumb, Button, Drawer, Empty, List, Popconfirm, Space, Tag, Tooltip, Typography } from "antd";
import React, { useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import { downloadText, messagePartsToMarkdown } from "../../download";
import type { ChartArtifact, ChatMessage, CitationSource, DocumentInfo, MessagePart, Session } from "../../types";
import { buildChartOption, chartTypeLabel } from "../../utils";

const { Text, Title } = Typography;

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

export function ChatView(props: ChatViewProps) {
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
            <div className="page-nav-row">
              <Breadcrumb className="page-breadcrumb" items={[{ title: "助手聊天" }]} />
            </div>
            <div className="page-title-block">
              <Title level={3}>{props.activeSession?.title || "新会话"}</Title>
              <Text type="secondary" className="page-subtitle">
                {props.documents.length
                  ? `已接入 ${props.documents.length} 个知识库文档`
                  : "上传文档后，可以直接围绕资料提问"}
              </Text>
            </div>
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
        className={`message-bubble ${isUser ? "user-bubble" : "assistant-bubble"} ${expanded ? "expanded" : "collapsed"}`}
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
          {!isUser && message.error && (
            <div className="message-error">{message.errorMessage || "请求失败，请稍后重试"}</div>
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
