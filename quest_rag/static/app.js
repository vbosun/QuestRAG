const STORAGE_KEY = "questrag.chat.sessions.v1";

const {
  App: AntApp,
  Avatar,
  Button,
  ConfigProvider,
  Empty,
  Input,
  Layout,
  List,
  Menu,
  Popconfirm,
  Space,
  Spin,
  Tag,
  Typography,
  Upload,
  message: messageApi,
} = antd;

const { Content, Sider } = Layout;
const { Text, Title } = Typography;
const { TextArea } = Input;
const { useEffect, useMemo, useRef, useState } = React;

function QuestRagApp() {
  return React.createElement(
    ConfigProvider,
    {
      theme: {
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
      },
    },
    React.createElement(
      AntApp,
      null,
      React.createElement(QuestRagWorkspace),
    ),
  );
}

function QuestRagWorkspace() {
  const [activeMenu, setActiveMenu] = useState("chat");
  const [sessions, setSessions] = useState(() => loadSessions());
  const [activeSessionId, setActiveSessionId] = useState(() => loadSessions()[0]?.id);
  const [sending, setSending] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [documentError, setDocumentError] = useState("");
  const [inputValue, setInputValue] = useState("");
  const messagesEndRef = useRef(null);

  const activeSession = useMemo(() => {
    return sessions.find((session) => session.id === activeSessionId) || sessions[0];
  }, [activeSessionId, sessions]);

  useEffect(() => {
    if (!sessions.length) {
      createSession();
      return;
    }
    if (!activeSessionId) {
      setActiveSessionId(sessions[0].id);
    }
  }, [sessions.length, activeSessionId]);

  useEffect(() => {
    saveSessions(sessions);
  }, [sessions]);

  useEffect(() => {
    loadDocuments();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: "end" });
  }, [activeSession?.messages.length, sending]);

  function createSession() {
    const now = new Date().toISOString();
    const session = {
      id: crypto.randomUUID(),
      title: "新会话",
      messages: [],
      uploads: [],
      createdAt: now,
      updatedAt: now,
    };
    setSessions((current) => [session, ...current]);
    setActiveSessionId(session.id);
    setActiveMenu("chat");
  }

  function deleteSession(id) {
    setSessions((current) => {
      if (current.length <= 1) {
        const next = createBlankSession();
        setActiveSessionId(next.id);
        return [next];
      }

      const next = current.filter((session) => session.id !== id);
      if (activeSessionId === id) {
        setActiveSessionId(next[0]?.id);
      }
      return next;
    });
  }

  function updateSession(sessionId, updater) {
    setSessions((current) =>
      current.map((session) =>
        session.id === sessionId ? updater({ ...session }) : session,
      ),
    );
  }

  async function sendMessage() {
    const text = inputValue.trim();
    const session = activeSession;
    if (!text || !session || sending) return;

    const userMessage = { role: "user", content: text };
    const requestHistory = [...session.messages, userMessage];
    setInputValue("");
    setSending(true);
    updateSession(session.id, (draft) => {
      draft.messages = requestHistory;
      draft.updatedAt = new Date().toISOString();
      if (draft.title === "新会话") {
        draft.title = text.slice(0, 24);
      }
      return draft;
    });

    try {
      const response = await fetch("/chat/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          session_id: session.id,
          history: requestHistory,
          stream: false,
        }),
      });
      const data = await readJson(response);
      if (!response.ok) {
        throw new Error(formatErrorDetail(data.detail) || "聊天请求失败");
      }

      setSessions((current) =>
        current.map((item) => {
          if (item.id !== session.id) return item;
          const nextId = data.session_id || item.id;
          setActiveSessionId(nextId);
          return {
            ...item,
            id: nextId,
            messages: [
              ...requestHistory,
              { role: "assistant", content: data.answer || "没有返回内容。" },
            ],
            updatedAt: new Date().toISOString(),
          };
        }),
      );
    } catch (error) {
      updateSession(session.id, (draft) => {
        draft.messages = [
          ...requestHistory,
          {
            role: "assistant",
            content: `请求失败：${error.message || "请稍后重试"}`,
            error: true,
          },
        ];
        draft.updatedAt = new Date().toISOString();
        return draft;
      });
    } finally {
      setSending(false);
    }
  }

  async function loadDocuments() {
    setLoadingDocuments(true);
    setDocumentError("");

    try {
      const response = await fetch("/documents/doclist", { method: "POST" });
      const data = await readJson(response);
      if (!response.ok) {
        throw new Error(formatErrorDetail(data.detail) || "读取文档失败");
      }
      setDocuments(Array.isArray(data) ? data : []);
    } catch (error) {
      setDocuments([]);
      setDocumentError(error.message || "读取文档失败");
    } finally {
      setLoadingDocuments(false);
    }
  }

  async function uploadFile(file, onSuccess, onError) {
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch("/documents/upload", {
        method: "POST",
        body: formData,
      });
      const data = await readJson(response);
      if (!response.ok || !data.success) {
        throw new Error(data.detail || data.message || "上传失败");
      }

      const session = activeSession;
      if (session) {
        updateSession(session.id, (draft) => {
          draft.uploads = [
            {
              filename: file.name,
              chunkCount: data.chunk_count,
              uploadedAt: new Date().toISOString(),
            },
            ...draft.uploads,
          ];
          draft.updatedAt = new Date().toISOString();
          return draft;
        });
      }

      messageApi.success(`${file.name} 上传完成，已索引 ${data.chunk_count} 个片段`);
      await loadDocuments();
      onSuccess?.(data);
    } catch (error) {
      messageApi.error(error.message || "上传失败");
      onError?.(error);
    }
  }

  async function deleteDocument(doc) {
    const name = doc.filename || doc.doc_id || "该文档";
    try {
      const response = await fetch("/documents/deletedoc", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: doc.doc_id }),
      });
      const data = await readJson(response);
      if (!response.ok || data.success === false) {
        throw new Error(formatErrorDetail(data.detail) || data.message || "删除失败");
      }
      messageApi.success(`${name} 已删除`);
      await loadDocuments();
    } catch (error) {
      messageApi.error(error.message || "删除失败");
    }
  }

  const navigationItems = [
    { key: "chat", label: "助手聊天" },
    { key: "knowledge", label: "知识库管理" },
  ];

  return React.createElement(
    Layout,
    { className: "app-shell" },
    React.createElement(
      Sider,
      {
        className: "app-sider",
        breakpoint: "lg",
        collapsedWidth: 0,
        width: 232,
      },
      React.createElement(
        "div",
        { className: "brand" },
        React.createElement("div", { className: "brand-mark" }, "Q"),
        React.createElement(
          "div",
          null,
          React.createElement(Title, { level: 4 }, "QuestRAG"),
          React.createElement(Text, { type: "secondary" }, "知识库问答工作台"),
        ),
      ),
      React.createElement(Menu, {
        mode: "inline",
        selectedKeys: [activeMenu],
        items: navigationItems,
        onClick: ({ key }) => setActiveMenu(key),
      }),
      React.createElement(
        "div",
        { className: "sider-summary" },
        React.createElement(Text, { type: "secondary" }, `${documents.length} 个文档`),
        React.createElement(Text, { type: "secondary" }, `${sessions.length} 个会话`),
      ),
    ),
    React.createElement(
      Content,
      { className: "app-content" },
      activeMenu === "chat"
        ? React.createElement(ChatView, {
            activeSession,
            documents,
            inputValue,
            messagesEndRef,
            onCreateSession: createSession,
            onDeleteSession: deleteSession,
            onInputChange: setInputValue,
            onSelectSession: setActiveSessionId,
            onSendMessage: sendMessage,
            onUploadFile: uploadFile,
            sending,
            sessions,
          })
        : React.createElement(KnowledgeView, {
            documents,
            documentError,
            loadingDocuments,
            onDeleteDocument: deleteDocument,
            onRefreshDocuments: loadDocuments,
            onUploadFile: uploadFile,
          }),
    ),
  );
}

function ChatView({
  activeSession,
  documents,
  inputValue,
  messagesEndRef,
  onCreateSession,
  onDeleteSession,
  onInputChange,
  onSelectSession,
  onSendMessage,
  onUploadFile,
  sending,
  sessions,
}) {
  const messages = activeSession?.messages || [];

  return React.createElement(
    "section",
    { className: "view-shell chat-view" },
    React.createElement(
      "aside",
      { className: "session-panel" },
      React.createElement(
        Space,
        { className: "section-title", direction: "vertical", size: 2 },
        React.createElement(Text, { strong: true }, "会话"),
        React.createElement(Text, { type: "secondary" }, "切换上下文记录"),
      ),
      React.createElement(
        Button,
        { block: true, type: "primary", onClick: onCreateSession },
        "新会话",
      ),
      React.createElement(SessionList, {
        activeSessionId: activeSession?.id,
        onDeleteSession,
        onSelectSession,
        sessions,
      }),
    ),
    React.createElement(
      "main",
      { className: "chat-panel" },
      React.createElement(
        "header",
        { className: "panel-header" },
        React.createElement(
          "div",
          null,
          React.createElement(Title, { level: 3 }, activeSession?.title || "新会话"),
          React.createElement(
            Text,
            { type: "secondary" },
            documents.length
              ? `已接入 ${documents.length} 个知识库文档`
              : "上传文档后，可以直接围绕资料提问",
          ),
        ),
        React.createElement(FileUploadButton, {
          buttonText: "上传文档",
          onUploadFile,
        }),
      ),
      React.createElement(
        "div",
        { className: "messages", "aria-live": "polite" },
        messages.length
          ? messages.map((message, index) =>
              React.createElement(ChatMessage, {
                key: `${message.role}-${index}`,
                message,
              }),
            )
          : React.createElement(Empty, {
              className: "chat-empty",
              description: "这里会显示当前会话的问答记录",
            }),
        sending &&
          React.createElement(
            "article",
            { className: "message-row assistant" },
            React.createElement(Avatar, { className: "message-avatar" }, "AI"),
            React.createElement(
              "div",
              { className: "message-bubble assistant-bubble" },
              React.createElement(Spin, { size: "small" }),
              React.createElement(Text, null, " 正在生成回答"),
            ),
          ),
        React.createElement("div", { ref: messagesEndRef }),
      ),
      React.createElement(
        "footer",
        { className: "composer" },
        React.createElement(TextArea, {
          autoSize: { minRows: 1, maxRows: 5 },
          disabled: sending,
          onChange: (event) => onInputChange(event.target.value),
          onPressEnter: (event) => {
            if (!event.shiftKey) {
              event.preventDefault();
              onSendMessage();
            }
          },
          placeholder: "输入问题，按 Enter 发送，Shift + Enter 换行",
          value: inputValue,
        }),
        React.createElement(
          Button,
          {
            disabled: !inputValue.trim(),
            loading: sending,
            onClick: onSendMessage,
            type: "primary",
          },
          "发送",
        ),
      ),
    ),
  );
}

function SessionList({ activeSessionId, onDeleteSession, onSelectSession, sessions }) {
  return React.createElement(List, {
    className: "session-list",
    dataSource: sessions,
    locale: { emptyText: "暂无会话" },
    renderItem: (session) =>
      React.createElement(
        List.Item,
        {
          className: session.id === activeSessionId ? "session-item active" : "session-item",
          onClick: () => onSelectSession(session.id),
        },
        React.createElement(
          "div",
          { className: "session-info" },
          React.createElement(Text, { strong: true, ellipsis: true }, session.title),
          React.createElement(
            Text,
            { type: "secondary" },
            session.messages.length ? `${session.messages.length} 条消息` : "尚未开始",
          ),
        ),
        React.createElement(
          Popconfirm,
          {
            cancelText: "取消",
            okButtonProps: { danger: true },
            okText: "删除",
            onConfirm: (event) => {
              event?.stopPropagation?.();
              onDeleteSession(session.id);
            },
            title: "删除这个会话？",
          },
          React.createElement(
            Button,
            {
              danger: true,
              size: "small",
              type: "text",
              onClick: (event) => event.stopPropagation(),
            },
            "删除",
          ),
        ),
      ),
  });
}

function ChatMessage({ message }) {
  const isUser = message.role === "user";
  return React.createElement(
    "article",
    { className: `message-row ${isUser ? "user" : "assistant"}` },
    !isUser && React.createElement(Avatar, { className: "message-avatar" }, "AI"),
    React.createElement(
      "div",
      {
        className: `message-bubble ${isUser ? "user-bubble" : "assistant-bubble"}${
          message.error ? " error-bubble" : ""
        }`,
      },
      message.content,
    ),
    isUser && React.createElement(Avatar, { className: "message-avatar user-avatar" }, "你"),
  );
}

function KnowledgeView({
  documents,
  documentError,
  loadingDocuments,
  onDeleteDocument,
  onRefreshDocuments,
  onUploadFile,
}) {
  return React.createElement(
    "section",
    { className: "view-shell knowledge-view" },
    React.createElement(
      "header",
      { className: "panel-header knowledge-header" },
      React.createElement(
        "div",
        null,
        React.createElement(Title, { level: 3 }, "知识库管理"),
        React.createElement(
          Text,
          { type: documentError ? "danger" : "secondary" },
          documentError || (documents.length ? `${documents.length} 个文档` : "暂无文档"),
        ),
      ),
      React.createElement(
        Space,
        { wrap: true },
        React.createElement(FileUploadButton, {
          buttonText: "上传文档",
          onUploadFile,
        }),
        React.createElement(
          Button,
          { onClick: onRefreshDocuments },
          "刷新",
        ),
      ),
    ),
    React.createElement(DocumentList, {
      documents,
      loadingDocuments,
      onDeleteDocument,
    }),
  );
}

function DocumentList({ documents, loadingDocuments, onDeleteDocument }) {
  if (loadingDocuments) {
    return React.createElement(
      "div",
      { className: "loading-panel" },
      React.createElement(Spin, null),
      React.createElement(Text, { type: "secondary" }, "正在读取文档"),
    );
  }

  return React.createElement(List, {
    className: "document-list",
    dataSource: documents,
    locale: {
      emptyText: React.createElement(Empty, { description: "还没有文档" }),
    },
    renderItem: (doc) => {
      const name = doc.filename || doc.doc_id || "未命名文档";
      return React.createElement(
        List.Item,
        {
          actions: [
            React.createElement(
              Popconfirm,
              {
                cancelText: "取消",
                key: "delete",
                okButtonProps: { danger: true },
                okText: "删除",
                onConfirm: () => onDeleteDocument(doc),
                title: `确认删除“${name}”？`,
              },
              React.createElement(Button, { danger: true, type: "link" }, "删除"),
            ),
          ],
        },
        React.createElement(
          List.Item.Meta,
          {
            avatar: React.createElement(Avatar, { className: "document-avatar" }, "文"),
            title: React.createElement(Text, { strong: true }, name),
            description: React.createElement(
              Space,
              { wrap: true, size: 8 },
              React.createElement(Tag, null, `${doc.chunk_count || 0} 个片段`),
              React.createElement(Text, { type: "secondary" }, formatDate(doc.uploaded_at)),
            ),
          },
        ),
      );
    },
  });
}

function FileUploadButton({ buttonText, onUploadFile }) {
  return React.createElement(
    Upload,
    {
      accept: ".txt,.pdf,.md",
      customRequest: ({ file, onError, onSuccess }) => {
        onUploadFile(file, onSuccess, onError);
      },
      maxCount: 1,
      showUploadList: false,
    },
    React.createElement(Button, { type: "primary" }, buttonText),
  );
}

function createBlankSession() {
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    title: "新会话",
    messages: [],
    uploads: [],
    createdAt: now,
    updatedAt: now,
  };
}

function loadSessions() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveSessions(sessions) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

function formatDate(value) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未知时间";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function readJson(response) {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

function formatErrorDetail(detail) {
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || JSON.stringify(item)).join("；");
  }
  if (detail && typeof detail === "object") {
    return detail.message || JSON.stringify(detail);
  }
  return detail;
}

ReactDOM.createRoot(document.querySelector("#root")).render(
  React.createElement(QuestRagApp),
);
