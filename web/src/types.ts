export type Role = "user" | "assistant";

export type ChartType = "pie" | "line" | "bar" | "scatter" | "radar" | "funnel" | "heatmap" | "bubble";

export interface DocumentInfo {
  doc_id: string;
  filename: string;
  chunk_count: number;
  token_count?: number;
  scope_code?: string;
  uploaded_at?: string;
  strategy?: string;
  separator_preset?: string;
}

export interface DocumentStats {
  document_count: number;
  total_chunks: number;
  total_text_length: number;
  total_token_count: number;
  max_text_length: number;
  min_text_length: number;
  format_distribution: Record<string, number>;
}

export interface DocumentChunk {
  chunk_id: string;
  text: string;
  metadata: Record<string, unknown>;
  length: number;
}

export interface DocumentMetadataInput {
  title: string;
  category: string;
  scope_code: string;
  organization?: string | null;
  publish_date?: string | null;
  region?: string | null;
  keywords: string[];
  notes?: string | null;
}

export interface CleanOptions {
  trim_lines: boolean;
  normalize_spaces: boolean;
  merge_blank_lines: boolean;
  merge_broken_lines: boolean;
}

export interface SplitOptions {
  chunk_size: number;
  chunk_overlap: number;
  attach_title: boolean;
  strategy: "fixed" | "structure" | "recursive";
  separator_preset: "general" | "chinese" | "english";
}

export interface RetrievalOptions {
  top_k: number;
  recall_k: number;
  mode: "hybrid" | "vector" | "keyword";
  rrf_k: number;
}

export interface GenerationConfig {
  temperature: number;
  top_p: number;
}

export interface GenerationOptions {
  model?: string | null;
  temperature: number;
  top_p: number;
  max_tokens: number;
  system_prompt_version: string;
  tool_policy: "current_user";
  seed?: number | null;
}

export interface RagasOptions {
  enabled: boolean;
  metrics: Array<"faithfulness" | "factual_correctness" | "response_relevancy" | "context_precision" | "context_recall">;
}

export interface EvaluationRun {
  id: string;
  name: string;
  status: string;
  dataset_path: string;
  es_index_name: string;
  retrieval_index_name?: string | null;
  evaluation_mode?: "retrieval" | "generation" | "both";
  document_scope: Record<string, unknown>;
  clean_options: Partial<CleanOptions>;
  split_options: Partial<SplitOptions>;
  retrieval_options: Partial<RetrievalOptions>;
  generation_options?: Partial<GenerationOptions>;
  ragas_options?: Partial<RagasOptions>;
  summary: Record<string, unknown>;
  error?: string | null;
  created_at: string;
  completed_at?: string | null;
  items?: EvaluationItem[];
}

export interface EvaluationItem {
  id: string;
  question_id?: string | null;
  question: string;
  expected_answer?: string | null;
  required_points?: string[];
  forbidden_claims?: string[];
  answer_type?: string | null;
  expected_citation_required?: boolean;
  expected_source_ids: string[];
  expected_chunk_ids: string[];
  expected_chunk_text?: string | null;
  should_refuse?: boolean;
  refusal_reason?: string | null;
  retrieval_queries?: Array<Record<string, unknown>>;
  retrieved: Array<Record<string, unknown>>;
  metrics: Record<string, unknown>;
  generated_answer?: string | null;
  answer_citations?: Array<Record<string, unknown>>;
  tool_calls?: Array<Record<string, unknown>>;
  generation_metrics?: Record<string, unknown>;
  ragas_metrics?: Record<string, unknown>;
  generation_error?: string | null;
  latency_ms?: number | null;
}

export interface EvaluationDocument {
  id: string;
  filename: string;
  title: string;
  file_type: string;
  file_size: number;
  metadata: Record<string, unknown>;
  chunk_count: number;
  latest_eval_run_id?: string | null;
  latest_eval_run_name?: string | null;
  latest_eval_chunk_count?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  chunks?: DocumentChunk[];
}

export interface EvaluationDocumentRun {
  id: string;
  name: string;
  status: string;
  es_index_name: string;
  clean_options: Partial<CleanOptions>;
  split_options: Partial<SplitOptions>;
  retrieval_options: Partial<RetrievalOptions>;
  summary: Record<string, unknown>;
  chunk_count: number;
  created_at?: string | null;
  completed_at?: string | null;
}

export interface EvaluationDatasetItem {
  id: string;
  question: string;
  expected_answer?: string | null;
  required_points?: string[];
  forbidden_claims?: string[];
  answer_type?: string | null;
  expected_citation_required?: boolean;
  expected_source_ids: string[];
  expected_evidence?: string | null;
  should_refuse: boolean;
  refusal_reason?: string | null;
  focus?: string | null;
  note?: string | null;
}

export interface EvaluationDataset {
  id: string;
  name: string;
  item_count?: number;
  items?: EvaluationDatasetItem[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DocumentStage {
  stage_id: string;
  filename: string;
  file_type: string;
  file_size: number;
  page_count: number;
  metadata: DocumentMetadataInput;
  clean_options: CleanOptions;
  split_options: SplitOptions;
  raw_preview: string;
  cleaned_preview: string;
  chunk_count: number;
  chunk_preview: Array<{
    index: number;
    text: string;
    length: number;
    page?: number | null;
    chunk_index?: number | null;
    heading_path?: string[];
  }>;
}

export interface DocumentCommitResult {
  success: boolean;
  doc_id: string;
  chunk_count: number;
  message: string;
}

export interface ChartDatum {
  name: string;
  value?: number | null;
  x?: number | null;
  y?: number | null;
  size?: number | null;
  series?: string | null;
}

export interface ChartArtifact {
  type: "chart";
  version: string;
  id: string;
  chart_type: ChartType;
  title: string;
  description?: string | null;
  data: ChartDatum[];
  encoding: {
    x: string;
    y: string;
    series?: string | null;
  };
  download?: {
    filename?: string;
  };
  source_note?: string | null;
}

export interface ReportArtifact {
  type: "report";
  version: string;
  id: string;
  title: string;
  content: string;
  download?: {
    filename?: string;
  };
}

export type Artifact = ChartArtifact | ReportArtifact;

export interface CitationSource {
  label: string;
  ref_id: string;
  source_type: "knowledge" | "job" | string;
  title: string;
  snippet: string;
  metadata: Record<string, unknown>;
  url?: string | null;
}

export type MessagePart =
  | { type: "markdown"; content: string }
  | { type: "chart"; artifact: ChartArtifact }
  | { type: "report"; artifact: ReportArtifact };

export interface ChatMessage {
  id: string;
  sequence?: number;
  role: Role;
  content?: string;
  raw?: string;
  parts?: MessagePart[];
  citations?: CitationSource[];
  status?: string;
  error?: boolean;
  errorMessage?: string;
}

export interface Session {
  id: string;
  title: string;
  messages: ChatMessage[];
  uploads: Array<{
    filename: string;
    chunkCount: number;
    uploadedAt: string;
  }>;
  createdAt: string;
  updatedAt: string;
}

export interface ConversationListResponse {
  items: Array<{
    id: string;
    title: string;
    created_at: string;
    updated_at: string;
  }>;
  total: number;
  page: number;
  page_size: number;
}

export interface ConversationDetail {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: Array<{
    id: string;
    sequence: number;
    role: Role;
    content: string;
    raw: string;
    parts: MessagePart[];
    citations: CitationSource[];
    status: string;
    error?: string | null;
    created_at: string;
  }>;
  tool_memories?: Array<Record<string, unknown>>;
}

export interface SocialSecuritySummary {
  insured_status: string;
  insured_unit?: string | null;
  first_insured_date?: string | null;
  current_base: number;
  total_payment_months: number;
  pension_account_balance: number;
  medical_account_balance: number;
  updated_at?: string | null;
}

export interface SocialSecurityPaymentRecord {
  payment_month: string;
  insurance_type: string;
  payment_base: number;
  personal_amount: number;
  company_amount: number;
  total_amount: number;
  paid_status: string;
  paid_at?: string | null;
}

export type StreamEvent =
  | { event: "meta"; data: { session_id: string } }
  | { event: "delta"; data: { text: string } }
  | { event: "status"; data: { message: string } }
  | { event: "sources"; data: { sources: CitationSource[] } }
  | { event: "artifact"; data: Artifact }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: { finish_reason: string } };
