const STORAGE_KEY = "questrag.chat.sessions.v1";

const sessionList = document.querySelector("#sessionList");
const messagesEl = document.querySelector("#messages");
const sessionTitle = document.querySelector("#sessionTitle");
const sessionMeta = document.querySelector("#sessionMeta");
const newSessionButton = document.querySelector("#newSessionButton");
const chatForm = document.querySelector("#chatForm");
const messageInput = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const fileInput = document.querySelector("#fileInput");
const uploadStatus = document.querySelector("#uploadStatus");

let sessions = loadSessions();
let activeSessionId = sessions[0]?.id;
let sending = false;

if (!activeSessionId) {
  createSession();
} else {
  render();
}

newSessionButton.addEventListener("click", () => {
  createSession();
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await sendMessage();
});

messageInput.addEventListener("keydown", async (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    await sendMessage();
  }
});

messageInput.addEventListener("input", () => {
  resizeMessageInput();
});

fileInput.addEventListener("change", async () => {
  const file = fileInput.files?.[0];
  if (!file) return;

  setUploadStatus(`正在上传 ${file.name} ...`);

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

    const session = getActiveSession();
    session.uploads.unshift({
      filename: file.name,
      chunkCount: data.chunk_count,
      uploadedAt: new Date().toISOString(),
    });
    session.updatedAt = new Date().toISOString();
    saveSessions();
    render();
    setUploadStatus(`${file.name} 上传完成，已索引 ${data.chunk_count} 个片段。`);
  } catch (error) {
    setUploadStatus(error.message || "上传失败", true);
  } finally {
    fileInput.value = "";
  }
});

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
  sessions.unshift(session);
  activeSessionId = session.id;
  saveSessions();
  render();
  messageInput.focus();
}

function deleteSession(id) {
  if (sessions.length === 1) {
    sessions = [];
    activeSessionId = undefined;
    createSession();
    return;
  }

  sessions = sessions.filter((session) => session.id !== id);
  if (activeSessionId === id) {
    activeSessionId = sessions[0].id;
  }
  saveSessions();
  render();
}

async function sendMessage() {
  const text = messageInput.value.trim();
  if (!text || sending) return;

  const session = getActiveSession();
  session.messages.push({ role: "user", content: text });
  session.updatedAt = new Date().toISOString();
  if (session.title === "新会话") {
    session.title = text.slice(0, 24);
  }

  messageInput.value = "";
  resetMessageInputHeight();
  sending = true;
  saveSessions();
  render();

  try {
    const response = await fetch("/chat/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        session_id: session.id,
        history: session.messages,
        stream: false,
      }),
    });
    const data = await readJson(response);
    if (!response.ok) {
      throw new Error(formatErrorDetail(data.detail) || "聊天请求失败");
    }

    session.messages.push({
      role: "assistant",
      content: data.answer || "没有返回内容。",
    });
    session.id = data.session_id || session.id;
    activeSessionId = session.id;
  } catch (error) {
    session.messages.push({
      role: "assistant",
      content: `请求失败：${error.message || "请稍后重试"}`,
      error: true,
    });
  } finally {
    session.updatedAt = new Date().toISOString();
    sending = false;
    saveSessions();
    render();
    messageInput.focus();
  }
}

function render() {
  const session = getActiveSession();
  sessionTitle.textContent = session.title;
  const uploadCount = session.uploads.length;
  sessionMeta.textContent = uploadCount
    ? `当前会话已上传 ${uploadCount} 个文件`
    : "上传文档后，直接围绕资料提问。";

  renderSessions();
  renderMessages(session);
  sendButton.disabled = sending;
  sendButton.textContent = sending ? "生成中" : "发送";
}

function renderSessions() {
  sessionList.replaceChildren(
    ...sessions.map((session) => {
      const item = document.createElement("div");
      item.className = "session-item";

      const tab = document.createElement("button");
      tab.className = `session-tab${session.id === activeSessionId ? " active" : ""}`;
      tab.type = "button";
      tab.addEventListener("click", () => {
        activeSessionId = session.id;
        saveSessions();
        render();
      });

      const title = document.createElement("strong");
      title.textContent = session.title;
      const meta = document.createElement("span");
      const messageCount = session.messages.length;
      meta.textContent = messageCount ? `${messageCount} 条消息` : "尚未开始";
      tab.append(title, meta);

      const remove = document.createElement("button");
      remove.className = "delete-session";
      remove.type = "button";
      remove.title = "删除会话";
      remove.textContent = "×";
      remove.addEventListener("click", () => deleteSession(session.id));

      item.append(tab, remove);
      return item;
    }),
  );
}

function renderMessages(session) {
  if (!session.messages.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent =
      "这里会显示当前会话的问答记录。可以先上传资料，也可以直接提问。";
    messagesEl.replaceChildren(empty);
    return;
  }

  messagesEl.replaceChildren(
    ...session.messages.map((message) => {
      const row = document.createElement("article");
      row.className = `message ${message.role}`;

      const role = document.createElement("div");
      role.className = "role";
      role.textContent = message.role === "user" ? "你" : "AI";

      const bubble = document.createElement("div");
      bubble.className = "bubble";
      bubble.textContent = message.content;

      row.append(role, bubble);
      return row;
    }),
  );
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function resizeMessageInput() {
  messageInput.style.height = "48px";
  const nextHeight = Math.min(Math.max(messageInput.scrollHeight, 48), 144);
  messageInput.style.height = `${nextHeight}px`;
}

function resetMessageInputHeight() {
  messageInput.style.height = "48px";
}

function setUploadStatus(message, isError = false) {
  uploadStatus.hidden = false;
  uploadStatus.textContent = message;
  uploadStatus.classList.toggle("error", isError);
}

function getActiveSession() {
  return sessions.find((session) => session.id === activeSessionId) || sessions[0];
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

function saveSessions() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
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
