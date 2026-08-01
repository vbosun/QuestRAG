import {
  BookOutlined,
  ClusterOutlined,
  ExperimentOutlined,
  LogoutOutlined,
  MessageOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { App, Avatar, Button, ConfigProvider, Dropdown, Layout, Menu, Result, Typography } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { deleteDocument, deleteEvaluation, listDocuments, listEvaluations, streamChat, uploadDocument } from "./api";
import { parseMessageParts } from "./artifacts";
import { AuthProvider, useAuth } from "./auth/AuthProvider";
import { ChangePasswordView } from "./auth/ChangePasswordView";
import { LoginPage } from "./auth/LoginPage";
import { filterMenuByPermissions } from "./auth/permissionUtils";
import { ProfileView } from "./auth/ProfileView";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { ChatView } from "./features/chat/ChatView";
import { EvaluationView } from "./features/evaluation/EvaluationView";
import { KnowledgeView } from "./features/knowledge/KnowledgeView";
import { RoleManagementView } from "./features/permissions/RoleManagementView";
import { SocialSecurityView } from "./features/publicServices/SocialSecurityView";
import { UserManagementView } from "./features/permissions/UserManagementView";
import { RetrievalConfigView } from "./features/retrieval/RetrievalConfigView";
import { clearTokens } from "./request";
import type { ChatMessage, DocumentInfo, EvaluationRun, Session } from "./types";
import { artifactToPart, createBlankSession, loadSessions, saveSessions } from "./utils";

const { Content, Sider, Header: AntHeader } = Layout;
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
            'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif',
        },
      }}
    >
      <App>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/app"
              element={
                <ProtectedRoute>
                  <WorkspaceLayout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Navigate to="/app/chat" replace />} />
              <Route path="chat" element={<ProtectedRoute permission="chat.view"><ChatPage /></ProtectedRoute>} />
              <Route path="knowledge" element={<ProtectedRoute permission="knowledge.view"><KnowledgePage /></ProtectedRoute>} />
              <Route path="evaluation" element={<ProtectedRoute permission="evaluation.view"><Navigate to="/app/evaluation/runs" replace /></ProtectedRoute>} />
              <Route path="evaluation/runs" element={<ProtectedRoute permission="evaluation.view"><EvalPage initialMode="list" /></ProtectedRoute>} />
              <Route path="evaluation/documents" element={<ProtectedRoute permission="evaluation.view"><EvalPage initialMode="documents" /></ProtectedRoute>} />
              <Route path="evaluation/datasets" element={<ProtectedRoute permission="evaluation.view"><EvalPage initialMode="datasets" /></ProtectedRoute>} />
              <Route path="retrieval-config" element={<ProtectedRoute permission="system.retrieval_config.view"><RetrievalConfigView /></ProtectedRoute>} />
              <Route path="profile" element={<ProtectedRoute permission="profile.view"><ProfileView /></ProtectedRoute>} />
              <Route path="profile/password" element={<ProtectedRoute permission="profile.view"><ChangePasswordView /></ProtectedRoute>} />
              <Route path="public-services/social-security" element={<ProtectedRoute permission="public_services.social_security.view"><SocialSecurityView /></ProtectedRoute>} />
              <Route path="permissions/users" element={<ProtectedRoute permission="permission.user.view"><UserManagementView /></ProtectedRoute>} />
              <Route path="permissions/roles" element={<ProtectedRoute permission="permission.role.view"><RoleManagementView /></ProtectedRoute>} />
            </Route>
            <Route path="/403" element={<ForbiddenPage />} />
            <Route path="*" element={<Navigate to="/app/chat" replace />} />
          </Routes>
        </AuthProvider>
      </App>
    </ConfigProvider>
  );
}

function buildMenuItems(navigate: ReturnType<typeof useNavigate>) {
  return [
    { key: "/app/chat", icon: <MessageOutlined />, label: "助手聊天", permission: "chat.view" },
    { key: "/app/knowledge", icon: <BookOutlined />, label: "知识库管理", permission: "knowledge.view" },
    {
      key: "evaluation",
      icon: <ExperimentOutlined />,
      label: "评测工作",
      permission: "evaluation.view",
      onTitleClick: () => navigate("/app/evaluation/runs", { state: { resetAt: Date.now() } }),
      children: [
        { key: "/app/evaluation/runs", label: "评测记录" },
        { key: "/app/evaluation/documents", label: "评测文档" },
        { key: "/app/evaluation/datasets", label: "评测集" },
      ],
    },
    { key: "/app/retrieval-config", icon: <SettingOutlined />, label: "检索配置", permission: "system.retrieval_config.view" },
    {
      key: "public-services",
      icon: <ClusterOutlined />,
      label: "政务工具",
      permission: "public_services.view",
      children: [
        { key: "/app/public-services/social-security", label: "社保查询", permission: "public_services.social_security.view" },
      ],
    },
    {
      key: "permissions",
      icon: <SafetyCertificateOutlined />,
      label: "权限管理",
      permission: "permission.manage",
      children: [
        { key: "/app/permissions/users", label: "用户管理", permission: "permission.user.view" },
        { key: "/app/permissions/roles", label: "角色管理", permission: "permission.role.view" },
      ],
    },
  ];
}

function ForbiddenPage() {
  return (
    <Result
      status="403"
      title="403"
      subTitle="抱歉，您没有权限访问此页面。"
      extra={
        <a href="/app/chat">
          <Button type="primary">返回首页</Button>
        </a>
      }
    />
  );
}

function WorkspaceLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, permissions, encryptAndLogout } = useAuth();
  const { message } = App.useApp();

  const allMenuItems = useMemo(() => buildMenuItems(navigate), [navigate]);
  const visibleMenuItems = useMemo(
    () => filterMenuByPermissions(allMenuItems, permissions),
    [allMenuItems, permissions],
  );

  const selectedKey = (() => {
    if (location.pathname.startsWith("/app/chat")) return "/app/chat";
    if (location.pathname.startsWith("/app/knowledge")) return "/app/knowledge";
    if (location.pathname.startsWith("/app/evaluation")) {
      if (location.pathname.includes("documents")) return "/app/evaluation/documents";
      if (location.pathname.includes("datasets")) return "/app/evaluation/datasets";
      return "/app/evaluation/runs";
    }
    if (location.pathname.startsWith("/app/retrieval-config")) return "/app/retrieval-config";
    if (location.pathname.startsWith("/app/public-services/social-security")) return "/app/public-services/social-security";
    if (location.pathname.startsWith("/app/permissions/users")) return "/app/permissions/users";
    if (location.pathname.startsWith("/app/permissions/roles")) return "/app/permissions/roles";
    if (location.pathname.startsWith("/app/profile")) return "/app/profile";
    return "/app/chat";
  })();

  async function handleLogout() {
    await encryptAndLogout();
    message.success("已退出登录");
    navigate("/login", { replace: true });
  }

  const userMenuItems = [
    { key: "profile", icon: <UserOutlined />, label: "个人管理" },
    { key: "logout", icon: <LogoutOutlined />, label: "退出登录", danger: true },
  ];

  function handleUserMenuClick({ key }: { key: string }) {
    if (key === "profile") navigate("/app/profile");
    if (key === "logout") handleLogout();
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
          defaultOpenKeys={["evaluation", "public-services", "permissions"]}
          mode="inline"
          selectedKeys={[selectedKey]}
          items={visibleMenuItems}
          onClick={({ key }) => {
            if (key.startsWith("/app/evaluation")) {
              navigate(key, { state: { resetAt: Date.now() } });
            } else {
              navigate(key);
            }
          }}
        />
        <div className="sider-summary">
          <Text type="secondary">{user?.full_name || ""}</Text>
        </div>
      </Sider>
      <Layout>
        <AntHeader
          style={{
            background: "#fff",
            padding: "0 24px",
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "center",
            borderBottom: "1px solid #f0f0f0",
          }}
        >
          <Dropdown menu={{ items: userMenuItems, onClick: handleUserMenuClick }} placement="bottomRight">
            <Button type="text" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Avatar size="small" icon={<UserOutlined />} />
              <span>{user?.full_name || ""}</span>
            </Button>
          </Dropdown>
        </AntHeader>
        <Content className="app-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}

function ChatPage() {
  const { message } = App.useApp();
  const [sessions, setSessions] = useState<Session[]>(() => loadSessions());
  const [activeSessionId, setActiveSessionId] = useState(() => loadSessions()[0]?.id);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [documentError, setDocumentError] = useState("");
  const [inputValue, setInputValue] = useState("");
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeSessionId) || sessions[0],
    [activeSessionId, sessions],
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
      current.map((s) => (s.id === sessionId ? updater({ ...s }) : s)),
    );
  }

  function createSession() {
    const session = createBlankSession();
    setSessions((current) => [session, ...current]);
    setActiveSessionId(session.id);
  }

  function removeSession(id: string) {
    setSessions((current) => {
      if (current.length <= 1) {
        const next = createBlankSession();
        setActiveSessionId(next.id);
        return [next];
      }
      const next = current.filter((s) => s.id !== id);
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
    const result: { chunk_count: number } = await uploadDocument(file);
    const session = activeSession;
    if (session) {
      updateSession(session.id, (draft) => ({
        ...draft,
        uploads: [
          { filename: file.name, chunkCount: result.chunk_count, uploadedAt: new Date().toISOString() },
          ...draft.uploads,
        ],
        updatedAt: new Date().toISOString(),
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

    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: "user", content: text };
    const assistantId = crypto.randomUUID();
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: "assistant",
      raw: "",
      parts: [{ type: "markdown", content: "" }],
      status: "正在准备回答...",
    };
    const nextMessages = [...session.messages, userMessage, assistantMessage];

    setInputValue("");
    setSending(true);
    updateSession(session.id, (draft) => ({
      ...draft,
      title: draft.title === "新会话" ? text.slice(0, 24) : draft.title,
      messages: nextMessages,
      updatedAt: new Date().toISOString(),
    }));

    try {
      await streamChat(
        { message: text, session_id: session.id, history: nextMessages },
        (event) => {
          if (event.event === "meta") { setActiveSessionId(event.data.session_id); return; }
          if (event.event === "delta") {
            updateAssistantMessage(session.id, assistantId, (current) => {
              const raw = `${current.raw || ""}${event.data.text}`;
              return { ...current, raw, parts: parseMessageParts(raw), status: undefined };
            });
            return;
          }
          if (event.event === "status") {
            updateAssistantMessage(session.id, assistantId, (current) => ({ ...current, status: event.data.message }));
            return;
          }
          if (event.event === "artifact") {
            updateAssistantMessage(session.id, assistantId, (current) => ({
              ...current,
              parts: [...(current.parts || []), artifactToPart(event.data)],
            }));
            return;
          }
          if (event.event === "sources") {
            updateAssistantMessage(session.id, assistantId, (current) => ({ ...current, citations: event.data.sources }));
            return;
          }
          if (event.event === "done") {
            updateAssistantMessage(session.id, assistantId, (current) => ({ ...current, status: undefined }));
            return;
          }
          if (event.event === "error") {
            updateAssistantMessage(session.id, assistantId, (current) => ({
              ...current,
              error: true,
              errorMessage: `请求失败：${event.data.message}`,
              status: undefined,
            }));
          }
        },
      );
    } catch (error) {
      updateAssistantMessage(session.id, assistantId, (current) => ({
        ...current,
        error: true,
        errorMessage: `请求失败：${error instanceof Error ? error.message : "请稍后重试"}`,
        status: undefined,
      }));
    } finally {
      setSending(false);
    }
  }

  function updateAssistantMessage(sessionId: string, messageId: string, updater: (m: ChatMessage) => ChatMessage) {
    updateSession(sessionId, (draft) => ({
      ...draft,
      messages: draft.messages.map((item) => (item.id === messageId ? updater(item) : item)),
      updatedAt: new Date().toISOString(),
    }));
  }

  return (
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
  );
}

function KnowledgePage() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [documentError, setDocumentError] = useState("");
  const { message } = App.useApp();

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

  useEffect(() => {
    void refreshDocuments();
  }, []);

  async function handleDeleteDocument(doc: DocumentInfo) {
    await deleteDocument(doc.doc_id);
    message.success(`${doc.filename || doc.doc_id} 已删除`);
    await refreshDocuments();
  }

  return (
    <KnowledgeView
      documents={documents}
      documentError={documentError}
      loadingDocuments={loadingDocuments}
      onDeleteDocument={handleDeleteDocument}
      onRefreshDocuments={refreshDocuments}
    />
  );
}

function EvalPage({ initialMode }: { initialMode: "list" | "documents" | "datasets" }) {
  const location = useLocation();
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [evaluations, setEvaluations] = useState<EvaluationRun[]>([]);
  const [evaluationError, setEvaluationError] = useState("");
  const [loadingEvaluations, setLoadingEvaluations] = useState(false);
  const { message } = App.useApp();
  const resetKey = (location.state as { resetAt?: number } | null)?.resetAt;

  async function refreshDocuments() {
    try {
      setDocuments(await listDocuments());
    } catch {
      setDocuments([]);
    }
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

  useEffect(() => {
    void refreshDocuments();
    void refreshEvaluations();
  }, []);

  async function handleDeleteEvaluation(run: EvaluationRun) {
    await deleteEvaluation(run.id);
    message.success(`${run.name} 已删除`);
    await refreshEvaluations();
  }

  return (
    <EvaluationView
      documents={documents}
      evaluationError={evaluationError}
      evaluations={evaluations}
      initialMode={initialMode}
      resetKey={resetKey}
      loadingEvaluations={loadingEvaluations}
      onDeleteEvaluation={handleDeleteEvaluation}
      onRefreshDocuments={refreshDocuments}
      onRefreshEvaluations={refreshEvaluations}
    />
  );
}
