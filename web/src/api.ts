import type {
  CleanOptions,
  DocumentCommitResult,
  DocumentChunk,
  DocumentInfo,
  DocumentMetadataInput,
  DocumentStats,
  EvaluationDataset,
  EvaluationDatasetItem,
  EvaluationDocument,
  EvaluationDocumentRun,
  EvaluationRun,
  RetrievalOptions,
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

export async function getDocumentStats(): Promise<DocumentStats> {
  const response = await fetch("/documents/stats", { method: "POST" });
  const data = await readJson(response);
  if (!response.ok) {
    throw new Error(formatErrorDetail(data.detail) || "读取统计信息失败");
  }
  return data as DocumentStats;
}

export async function listEvaluations(): Promise<EvaluationRun[]> {
  const response = await fetch("/evaluations", { method: "POST" });
  const data = await readJson(response);
  if (!response.ok) {
    throw new Error(formatErrorDetail(data.detail) || "读取评测记录失败");
  }
  return Array.isArray(data) ? data : [];
}

export async function getEvaluation(id: string): Promise<EvaluationRun> {
  const response = await fetch("/evaluations/runs/get", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: id }),
  });
  const data = await readJson(response);
  if (!response.ok) {
    throw new Error(formatErrorDetail(data.detail) || "读取评测详情失败");
  }
  return data as EvaluationRun;
}

export async function deleteEvaluation(id: string) {
  const response = await fetch("/evaluations/runs/delete", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: id }),
  });
  const data = await readJson(response);
  if (!response.ok || data.success === false) {
    throw new Error(formatErrorDetail(data.detail) || data.message || "删除评测失败");
  }
  return data;
}

export async function listEvaluationDocuments(): Promise<EvaluationDocument[]> {
  const response = await fetch("/evaluations/documents/list", { method: "POST" });
  const data = await readJson(response);
  if (!response.ok) throw new Error(formatErrorDetail(data.detail) || "读取评测文档失败");
  return Array.isArray(data) ? data : [];
}

export async function uploadEvaluationDocuments(files: File[]): Promise<EvaluationDocument[]> {
  const formData = new FormData();
  for (const file of files) formData.append("files", file);
  const response = await fetch("/evaluations/documents/upload", { method: "POST", body: formData });
  const data = await readJson(response);
  if (!response.ok) throw new Error(formatErrorDetail(data.detail) || "上传评测文档失败");
  return Array.isArray(data) ? data : [];
}

export async function getEvaluationDocument(id: string): Promise<EvaluationDocument> {
  const response = await fetch("/evaluations/documents/get", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: id }),
  });
  const data = await readJson(response);
  if (!response.ok) throw new Error(formatErrorDetail(data.detail) || "读取评测文档失败");
  return data as EvaluationDocument;
}

export async function listEvaluationDocumentRuns(id: string): Promise<EvaluationDocumentRun[]> {
  const response = await fetch("/evaluations/documents/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: id }),
  });
  const data = await readJson(response);
  if (!response.ok) throw new Error(formatErrorDetail(data.detail) || "读取评测文档记录失败");
  return Array.isArray(data) ? data : [];
}

export async function listEvaluationDocumentRunChunks(id: string, runId: string): Promise<DocumentChunk[]> {
  const response = await fetch("/evaluations/documents/runs/chunks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: id, run_id: runId }),
  });
  const data = await readJson(response);
  if (!response.ok) throw new Error(formatErrorDetail(data.detail) || "读取评测分块失败");
  return Array.isArray(data) ? data : [];
}

export async function deleteEvaluationDocument(id: string) {
  const response = await fetch("/evaluations/documents/delete", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: id }),
  });
  const data = await readJson(response);
  if (!response.ok || data.success === false) throw new Error(formatErrorDetail(data.detail) || data.message || "删除评测文档失败");
  return data;
}

export async function listEvaluationDatasets(): Promise<EvaluationDataset[]> {
  const response = await fetch("/evaluations/datasets/list", { method: "POST" });
  const data = await readJson(response);
  if (!response.ok) throw new Error(formatErrorDetail(data.detail) || "读取评测集失败");
  return Array.isArray(data) ? data : [];
}

export async function importEvaluationDataset(file: File): Promise<EvaluationDataset> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch("/evaluations/datasets/import", { method: "POST", body: formData });
  const data = await readJson(response);
  if (!response.ok) throw new Error(formatErrorDetail(data.detail) || "导入评测集失败");
  return data as EvaluationDataset;
}

export async function createEvaluationDataset(payload: { name: string; items: EvaluationDatasetItem[] }): Promise<EvaluationDataset> {
  const response = await fetch("/evaluations/datasets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const data = await readJson(response);
  if (!response.ok) throw new Error(formatErrorDetail(data.detail) || "新建评测集失败");
  return data as EvaluationDataset;
}

export async function getEvaluationDataset(id: string): Promise<EvaluationDataset> {
  const response = await fetch("/evaluations/datasets/get", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_id: id }),
  });
  const data = await readJson(response);
  if (!response.ok) throw new Error(formatErrorDetail(data.detail) || "读取评测集失败");
  return data as EvaluationDataset;
}

export async function updateEvaluationDataset(id: string, payload: { name: string; items: EvaluationDatasetItem[] }): Promise<EvaluationDataset> {
  const response = await fetch("/evaluations/datasets/update", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_id: id, ...payload }),
  });
  const data = await readJson(response);
  if (!response.ok) throw new Error(formatErrorDetail(data.detail) || "保存评测集失败");
  return data as EvaluationDataset;
}

export async function deleteEvaluationDataset(id: string) {
  const response = await fetch("/evaluations/datasets/delete", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_id: id }),
  });
  const data = await readJson(response);
  if (!response.ok || data.success === false) throw new Error(formatErrorDetail(data.detail) || data.message || "删除评测集失败");
  return data;
}

export async function exportEvaluationDataset(id: string): Promise<Blob> {
  const response = await fetch("/evaluations/datasets/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_id: id }),
  });
  if (!response.ok) {
    const data = await readJson(response);
    throw new Error(formatErrorDetail(data.detail) || "导出评测集失败");
  }
  return response.blob();
}

export async function runEvaluation(payload: {
  name: string;
  dataset_id: string;
  document_ids: string[];
  clean_options: CleanOptions;
  split_options: SplitOptions;
  retrieval_options: RetrievalOptions;
}): Promise<EvaluationRun> {
  const response = await fetch("/evaluations/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const data = await readJson(response);
  if (!response.ok) {
    throw new Error(formatErrorDetail(data.detail) || "评测运行失败");
  }
  return data as EvaluationRun;
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

export async function getRetrievalConfig(): Promise<RetrievalOptions> {
  const response = await fetch("/system/config/retrieval");
  const data = await readJson(response);
  if (!response.ok) {
    throw new Error(formatErrorDetail(data.detail) || "读取检索配置失败");
  }
  return data as RetrievalOptions;
}

export async function updateRetrievalConfig(params: RetrievalOptions) {
  const response = await fetch("/system/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key: "retrieval", value: params }),
  });
  const data = await readJson(response);
  if (!response.ok) {
    throw new Error(formatErrorDetail(data.detail) || "保存检索配置失败");
  }
  return data;
}

export async function syncRetrievalConfig(runId: string) {
  const response = await fetch("/system/config/retrieval/sync", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId }),
  });
  const data = await readJson(response);
  if (!response.ok) {
    throw new Error(formatErrorDetail(data.detail) || "同步检索配置失败");
  }
  return data;
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
