import type {
  CleanOptions,
  DocumentCommitResult,
  DocumentChunk,
  DocumentInfo,
  DocumentMetadataInput,
  DocumentStage,
  SplitOptions,
  StreamEvent
} from "./types";

export async function listDocuments(): Promise<DocumentInfo[]> {
  const response = await fetch("/documents/doclist", { method: "POST" });
  const data = await readJson(response);
  if (!response.ok) {
    throw new Error(formatErrorDetail(data.detail) || "读取文档失败");
  }
  return Array.isArray(data) ? data : [];
}

export async function uploadDocument(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch("/documents/upload", {
    method: "POST",
    body: formData
  });
  const data = await readJson(response);
  if (!response.ok || !data.success) {
    throw new Error(data.detail || data.message || "上传失败");
  }
  return data;
}

export async function stageDocument(file: File): Promise<DocumentStage> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch("/documents/stage", {
    method: "POST",
    body: formData
  });
  const data = await readJson(response);
  if (!response.ok) {
    throw new Error(formatErrorDetail(data.detail) || "文档解析失败");
  }
  return data as DocumentStage;
}

export async function previewDocumentStage(payload: {
  stage_id: string;
  metadata: DocumentMetadataInput;
  clean_options: CleanOptions;
  split_options: SplitOptions;
  replace_doc_id?: string;
}): Promise<DocumentStage> {
  const response = await fetch("/documents/stage/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const data = await readJson(response);
  if (!response.ok) {
    throw new Error(formatErrorDetail(data.detail) || "生成预览失败");
  }
  return data as DocumentStage;
}

export async function commitDocumentStage(payload: {
  stage_id: string;
  metadata: DocumentMetadataInput;
  clean_options: CleanOptions;
  split_options: SplitOptions;
  replace_doc_id?: string;
}): Promise<DocumentCommitResult> {
  const response = await fetch("/documents/stage/commit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const data = await readJson(response);
  if (!response.ok || data.success === false) {
    throw new Error(formatErrorDetail(data.detail) || data.message || "入库失败");
  }
  return data as DocumentCommitResult;
}

export async function deleteDocument(docId: string) {
  const response = await fetch("/documents/deletedoc", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: docId })
  });
  const data = await readJson(response);
  if (!response.ok || data.success === false) {
    throw new Error(formatErrorDetail(data.detail) || data.message || "删除失败");
  }
  return data;
}

export async function listDocumentChunks(docId: string): Promise<DocumentChunk[]> {
  const response = await fetch("/documents/chunks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: docId })
  });
  const data = await readJson(response);
  if (!response.ok) {
    throw new Error(formatErrorDetail(data.detail) || "读取分块失败");
  }
  return Array.isArray(data) ? data : [];
}

export async function streamChat(
  payload: {
    message: string;
    session_id: string;
    history: unknown[];
  },
  onEvent: (event: StreamEvent) => void
) {
  const response = await fetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...payload,
      stream: true
    })
  });

  if (!response.ok || !response.body) {
    const data = await readJson(response);
    throw new Error(formatErrorDetail(data.detail) || "聊天请求失败");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const event = parseSseFrame(frame);
      if (event) onEvent(event);
    }
  }

  if (buffer.trim()) {
    const event = parseSseFrame(buffer);
    if (event) onEvent(event);
  }
}

function parseSseFrame(frame: string): StreamEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) } as StreamEvent;
  } catch {
    return null;
  }
}

async function readJson(response: Response) {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

function formatErrorDetail(detail: unknown) {
  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg || JSON.stringify(item)).join("；");
  }
  if (detail && typeof detail === "object") {
    const value = detail as { message?: string };
    return value.message || JSON.stringify(detail);
  }
  return typeof detail === "string" ? detail : "";
}
