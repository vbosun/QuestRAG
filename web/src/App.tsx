import { BookOutlined, ExperimentOutlined, MessageOutlined } from "@ant-design/icons";
import { App, ConfigProvider, Layout, Menu, Typography } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { deleteDocument, deleteEvaluation, listDocuments, listEvaluations, streamChat, uploadDocument } from "./api";
import { parseMessageParts } from "./artifacts";
import { ChatView } from "./features/chat/ChatView";
import { EvaluationView } from "./features/evaluation/EvaluationView";
import { KnowledgeView } from "./features/knowledge/KnowledgeView";
import type { ChatMessage, DocumentInfo, EvaluationRun, Session } from "./types";
import { artifactToPart, createBlankSession, loadSessions, saveSessions } from "./utils";

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
  const [evaluations, setEvaluations] = useState<EvaluationRun[]>([]);
  const [evaluationError, setEvaluationError] = useState("");
  const [loadingEvaluations, setLoadingEvaluations] = useState(false);
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
    void refreshEvaluations();
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

  async function refreshEvaluations() {
    setLoadingEvaluations(true);
    setEvaluationError("");
    try {
      setEvaluations(await listEvaluations());
    } catch (error) {
      setEvaluations([]);
      setEvaluationError(error instanceof Error ? error.message : "读取评测记录失败");
    } finally {
      setLoadingEvaluations(false);
    }
  }

  async function handleDeleteEvaluation(run: EvaluationRun) {
    await deleteEvaluation(run.id);
    message.success(`${run.name} 已删除`);
    await refreshEvaluations();
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
          defaultOpenKeys={["evaluation"]}
          mode="inline"
          selectedKeys={[activeMenu]}
          items={[
            { key: "chat", icon: <MessageOutlined />, label: "助手聊天" },
            { key: "knowledge", icon: <BookOutlined />, label: "知识库管理" },
            {
              key: "evaluation",
              icon: <ExperimentOutlined />,
              label: "评测工作",
              children: [
                { key: "evaluation-runs", label: "评测记录" },
                { key: "evaluation-documents", label: "评测文档" },
                { key: "evaluation-datasets", label: "评测集" }
              ]
            }
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
        ) : activeMenu === "knowledge" ? (
          <KnowledgeView
            documents={documents}
            documentError={documentError}
            loadingDocuments={loadingDocuments}
            onDeleteDocument={handleDeleteDocument}
            onRefreshDocuments={refreshDocuments}
          />
        ) : (
          <EvaluationView
            documents={documents}
            evaluationError={evaluationError}
            evaluations={evaluations}
            initialMode={
              activeMenu === "evaluation-documents"
                ? "documents"
                : activeMenu === "evaluation-datasets"
                  ? "datasets"
                  : "list"
            }
            loadingEvaluations={loadingEvaluations}
            onDeleteEvaluation={handleDeleteEvaluation}
            onRefreshDocuments={refreshDocuments}
            onRefreshEvaluations={refreshEvaluations}
          />
        )}
      </Content>
    </Layout>
  );
}
