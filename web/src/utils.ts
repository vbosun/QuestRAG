import type { Artifact, ChartArtifact, MessagePart, Session } from "./types";

const STORAGE_KEY = "questrag.chat.sessions.v2";

export function artifactToPart(artifact: Artifact): MessagePart {
  if (artifact.type === "chart") return { type: "chart", artifact };
  return { type: "report", artifact };
}

export function buildChartOption(artifact: ChartArtifact) {
  if (artifact.chart_type === "pie") {
    return {
      tooltip: { trigger: "item" },
      legend: { bottom: 0 },
      series: [
        {
          name: artifact.title,
          type: "pie",
          radius: ["38%", "68%"],
          data: artifact.data.map((item) => ({ name: item.name, value: item.value }))
        }
      ]
    };
  }

  const xAxis = Array.from(new Set(artifact.data.map((item) => item.name)));
  const groups = Array.from(new Set(artifact.data.map((item) => item.series || artifact.title)));
  const series = groups.map((group) => ({
    name: group,
    type: artifact.chart_type,
    smooth: artifact.chart_type === "line",
    data: xAxis.map((name) => {
      const item = artifact.data.find((entry) => entry.name === name && (entry.series || artifact.title) === group);
      return item?.value ?? 0;
    })
  }));

  return {
    tooltip: { trigger: "axis" },
    legend: { bottom: 0 },
    grid: { left: 36, right: 18, top: 28, bottom: 56 },
    xAxis: { type: "category", data: xAxis },
    yAxis: { type: "value" },
    series
  };
}

export function chartTypeLabel(type: ChartArtifact["chart_type"]) {
  return { pie: "饼图", line: "折线图", bar: "柱状图" }[type];
}

export function createBlankSession(): Session {
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    title: "新会话",
    messages: [],
    uploads: [],
    createdAt: now,
    updatedAt: now
  };
}

export function loadSessions(): Session[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveSessions(sessions: Session[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

export function formatDate(value?: string) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未知时间";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export function formatRate(value: unknown) {
  if (typeof value !== "number") return "-";
  return `${Math.round(value * 1000) / 10}%`;
}

export function evalStatusLabel(status: string) {
  return { completed: "已完成", failed: "失败", running: "运行中" }[status] || status;
}

export function summarizeRetrieved(retrieved: Array<Record<string, unknown>>) {
  if (!retrieved?.length) return "无";
  return retrieved
    .slice(0, 3)
    .map((item) => `#${String(item.rank)} ${String(item.filename || item.doc_id || "未知")} ${String(item.score ?? "")}`)
    .join("；");
}

export function formatFileSize(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

export function documentExt(value: string) {
  const ext = value.includes(".") ? value.split(".").pop()?.toUpperCase() : "DOC";
  return ext?.slice(0, 3) || "DOC";
}
