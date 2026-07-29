export type Role = "user" | "assistant";

export type ChartType = "pie" | "line" | "bar";

export interface DocumentInfo {
  doc_id: string;
  filename: string;
  chunk_count: number;
  uploaded_at?: string;
}

export interface ChartDatum {
  name: string;
  value: number;
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
  role: Role;
  content?: string;
  raw?: string;
  parts?: MessagePart[];
  citations?: CitationSource[];
  status?: string;
  error?: boolean;
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

export type StreamEvent =
  | { event: "meta"; data: { session_id: string } }
  | { event: "delta"; data: { text: string } }
  | { event: "status"; data: { message: string } }
  | { event: "sources"; data: { sources: CitationSource[] } }
  | { event: "artifact"; data: Artifact }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: { finish_reason: string } };
