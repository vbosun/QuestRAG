import { request, requestJson } from "./request";
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
  StreamEvent,
} from "./types";

function postJson<T = unknown>(path: string, body?: unknown): Promise<T> {
  return requestJson<T>(path, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
}

function putJson<T = unknown>(path: string, body?: unknown): Promise<T> {
  return requestJson<T>(path, {
    method: "PUT",
    body: body ? JSON.stringify(body) : undefined,
  });
}

function delJson<T = unknown>(path: string, body?: unknown): Promise<T> {
  return requestJson<T>(path, {
    method: "DELETE",
    body: body ? JSON.stringify(body) : undefined,
  });
}

function getJson<T = unknown>(path: string): Promise<T> {
  return requestJson<T>(path, { method: "GET" });
}

export async function listDocuments(): Promise<DocumentInfo[]> {
  const data = await postJson<DocumentInfo[]>("/documents/doclist");
  return Array.isArray(data) ? data : [];
}

export async function getDocumentStats(): Promise<DocumentStats> {
  return postJson<DocumentStats>("/documents/stats");
}

export async function listEvaluations(): Promise<EvaluationRun[]> {
  const data = await postJson<EvaluationRun[]>("/evaluations");
  return Array.isArray(data) ? data : [];
}

export async function getEvaluation(id: string): Promise<EvaluationRun> {
  return postJson<EvaluationRun>("/evaluations/runs/get", { run_id: id });
}

export async function deleteEvaluation(id: string) {
  return delJson("/evaluations/runs/delete", { run_id: id });
}

export async function listEvaluationDocuments(): Promise<EvaluationDocument[]> {
  const data = await postJson<EvaluationDocument[]>("/evaluations/documents/list");
  return Array.isArray(data) ? data : [];
}

export async function uploadEvaluationDocuments(files: File[]): Promise<EvaluationDocument[]> {
  const formData = new FormData();
  for (const file of files) formData.append("files", file);
  const data = await requestJson<EvaluationDocument[]>("/evaluations/documents/upload", {
    method: "POST",
    body: formData,
  });
  return Array.isArray(data) ? data : [];
}

export async function getEvaluationDocument(id: string): Promise<EvaluationDocument> {
  return postJson<EvaluationDocument>("/evaluations/documents/get", { doc_id: id });
}

export async function listEvaluationDocumentRuns(id: string): Promise<EvaluationDocumentRun[]> {
  const data = await postJson<EvaluationDocumentRun[]>("/evaluations/documents/runs", { doc_id: id });
  return Array.isArray(data) ? data : [];
}

export async function listEvaluationDocumentRunChunks(id: string, runId: string): Promise<DocumentChunk[]> {
  const data = await postJson<DocumentChunk[]>("/evaluations/documents/runs/chunks", { doc_id: id, run_id: runId });
  return Array.isArray(data) ? data : [];
}

export async function deleteEvaluationDocument(id: string) {
  return delJson("/evaluations/documents/delete", { doc_id: id });
}

export async function listEvaluationDatasets(): Promise<EvaluationDataset[]> {
  const data = await postJson<EvaluationDataset[]>("/evaluations/datasets/list");
  return Array.isArray(data) ? data : [];
}

export async function importEvaluationDataset(file: File): Promise<EvaluationDataset> {
  const formData = new FormData();
  formData.append("file", file);
  return requestJson<EvaluationDataset>("/evaluations/datasets/import", {
    method: "POST",
    body: formData,
  });
}

export async function createEvaluationDataset(payload: { name: string; items: EvaluationDatasetItem[] }): Promise<EvaluationDataset> {
  return postJson<EvaluationDataset>("/evaluations/datasets", payload);
}

export async function getEvaluationDataset(id: string): Promise<EvaluationDataset> {
  return postJson<EvaluationDataset>("/evaluations/datasets/get", { dataset_id: id });
}

export async function updateEvaluationDataset(id: string, payload: { name: string; items: EvaluationDatasetItem[] }): Promise<EvaluationDataset> {
  return putJson<EvaluationDataset>("/evaluations/datasets/update", { dataset_id: id, ...payload });
}

export async function deleteEvaluationDataset(id: string) {
  return delJson("/evaluations/datasets/delete", { dataset_id: id });
}

export async function exportEvaluationDataset(id: string): Promise<Blob> {
  const response = await request("/evaluations/datasets/export", {
    method: "POST",
    body: JSON.stringify({ dataset_id: id }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "导出评测集失败");
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
  return postJson<EvaluationRun>("/evaluations/run", payload);
}

export async function uploadDocument(file: File): Promise<{ success: boolean; chunk_count: number; doc_id: string; message: string }> {
  const formData = new FormData();
  formData.append("file", file);
  return requestJson("/documents/upload", { method: "POST", body: formData });
}

export async function stageDocument(file: File): Promise<DocumentStage> {
  const formData = new FormData();
  formData.append("file", file);
  return requestJson<DocumentStage>("/documents/stage", { method: "POST", body: formData });
}

export async function previewDocumentStage(payload: {
  stage_id: string;
  metadata: DocumentMetadataInput;
  clean_options: CleanOptions;
  split_options: SplitOptions;
  replace_doc_id?: string;
}): Promise<DocumentStage> {
  return postJson<DocumentStage>("/documents/stage/preview", payload);
}

export async function commitDocumentStage(payload: {
  stage_id: string;
  metadata: DocumentMetadataInput;
  clean_options: CleanOptions;
  split_options: SplitOptions;
  replace_doc_id?: string;
}): Promise<DocumentCommitResult> {
  return postJson<DocumentCommitResult>("/documents/stage/commit", payload);
}

export async function deleteDocument(docId: string) {
  return postJson("/documents/deletedoc", { id: docId });
}

export async function listDocumentChunks(docId: string): Promise<DocumentChunk[]> {
  const data = await postJson<DocumentChunk[]>("/documents/chunks", { id: docId });
  return Array.isArray(data) ? data : [];
}

export async function streamChat(
  payload: { message: string; session_id: string; history: unknown[] },
  onEvent: (event: StreamEvent) => void,
) {
  const response = await request("/chat/stream", {
    method: "POST",
    body: JSON.stringify({ ...payload, stream: true }),
  });

  if (!response.ok || !response.body) {
    throw new Error("聊天请求失败");
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
  return getJson<RetrievalOptions>("/system/config/retrieval");
}

export async function updateRetrievalConfig(params: RetrievalOptions) {
  return putJson("/system/config", { key: "retrieval", value: params });
}

export async function syncRetrievalConfig(runId: string) {
  return postJson("/system/config/retrieval/sync", { run_id: runId });
}
