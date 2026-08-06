import { request, requestJson } from "./request";
import type {
  CleanOptions,
  ConversationDetail,
  ConversationListResponse,
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
  GenerationConfig,
  GenerationOptions,
  RagasOptions,
  RetrievalOptions,
  SocialSecurityPaymentRecord,
  SocialSecuritySummary,
  DocumentStage,
  SplitOptions,
  StreamEvent,
} from "./types";
import type { PermissionCatalog, RoleDetail, RoleInfo, UserListResponse } from "./features/permissions/types";

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

export async function downloadEvaluationDatasetTemplate(): Promise<Blob> {
  const response = await request("/evaluations/datasets/template", {
    method: "POST",
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "下载评测集模板失败");
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
  evaluation_mode: "retrieval" | "generation" | "both";
  generation_options: GenerationOptions;
  ragas_options: RagasOptions;
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

export function listChatConversations(params?: { page?: number; page_size?: number }): Promise<ConversationListResponse> {
  return postJson<ConversationListResponse>("/chat/conversations/list", {
    page: params?.page || 1,
    page_size: params?.page_size || 30,
  });
}

export function createChatConversation(payload?: { title?: string }): Promise<ConversationDetail> {
  return postJson<ConversationDetail>("/chat/conversations/create", { title: payload?.title || "新会话" });
}

export function getChatConversation(conversationId: string): Promise<ConversationDetail> {
  return postJson<ConversationDetail>("/chat/conversations/get", { conversation_id: conversationId });
}

export function deleteChatConversation(conversationId: string): Promise<{ success: boolean }> {
  return postJson<{ success: boolean }>("/chat/conversations/delete", { conversation_id: conversationId });
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

export async function getGenerationConfig(): Promise<GenerationConfig> {
  return getJson<GenerationConfig>("/system/config/generation");
}

export async function updateGenerationConfig(params: GenerationConfig) {
  return putJson("/system/config", { key: "generation", value: params });
}

export async function syncRetrievalConfig(runId: string) {
  return postJson("/system/config/retrieval/sync", { run_id: runId });
}

// ── 权限管理 ──────────────────────────────────────────────────────────

export function listPermissionCatalog(): Promise<PermissionCatalog> {
  return postJson<PermissionCatalog>("/permissions/catalog", {});
}

export function listRoles(): Promise<RoleInfo[]> {
  return postJson<RoleInfo[]>("/permissions/roles/list", {});
}

export function getRole(id: number): Promise<RoleDetail> {
  return postJson<RoleDetail>("/permissions/roles/get", { role_id: id });
}

export function createRole(payload: { code: string; name: string; description?: string }): Promise<RoleInfo> {
  return postJson<RoleInfo>("/permissions/roles/create", payload);
}

export function updateRole(id: number, payload: { name?: string; description?: string; status?: number }): Promise<RoleInfo> {
  return postJson<RoleInfo>("/permissions/roles/update", { role_id: id, ...payload });
}

export function deleteRole(id: number): Promise<unknown> {
  return postJson("/permissions/roles/delete", { role_id: id });
}

export function updateRolePermissions(id: number, codes: string[]): Promise<unknown> {
  return postJson("/permissions/roles/permissions", { role_id: id, codes });
}

export function updateRoleRagScopes(id: number, codes: string[]): Promise<unknown> {
  return postJson("/permissions/roles/rag-scopes", { role_id: id, codes });
}

export function listUsers(params?: {
  search?: string;
  role_code?: string;
  status?: number;
  page?: number;
  page_size?: number;
}): Promise<UserListResponse> {
  return postJson<UserListResponse>("/permissions/users/list", params || {});
}

export function createUser(payload: { full_name: string; id_number: string; password: string; role_codes?: string[] }): Promise<{ id: number }> {
  return postJson("/permissions/users/create", payload);
}

export function updateUserRoles(userId: number, role_codes: string[]): Promise<unknown> {
  return postJson("/permissions/users/roles", { user_id: userId, role_codes });
}

export function resetUserPassword(userId: number, new_password: string): Promise<unknown> {
  return postJson("/permissions/users/reset-password", { user_id: userId, new_password });
}

export function lockUser(userId: number): Promise<unknown> {
  return postJson("/permissions/users/lock", { user_id: userId });
}

export function unlockUser(userId: number): Promise<unknown> {
  return postJson("/permissions/users/unlock", { user_id: userId });
}

export function enableUser(userId: number): Promise<unknown> {
  return postJson("/permissions/users/enable", { user_id: userId });
}

export function disableUser(userId: number): Promise<unknown> {
  return postJson("/permissions/users/disable", { user_id: userId });
}

export function kickUser(userId: number): Promise<unknown> {
  return postJson("/permissions/users/kick", { user_id: userId });
}

// ── 政务工具 ──────────────────────────────────────────────────────────

export function getSocialSecuritySummary(): Promise<SocialSecuritySummary> {
  return postJson<SocialSecuritySummary>("/public-services/social-security/summary", {});
}

export function listSocialSecurityPayments(params?: {
  insurance_type?: string;
  start_month?: string;
  end_month?: string;
  limit?: number;
}): Promise<SocialSecurityPaymentRecord[]> {
  return postJson<SocialSecurityPaymentRecord[]>("/public-services/social-security/payments", params || {});
}
