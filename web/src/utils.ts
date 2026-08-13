import type { Artifact, ChartArtifact, MessagePart, Session } from "./types";

const STORAGE_KEY = "questrag.chat.sessions.v2";

export function artifactToPart(artifact: Artifact): MessagePart {
  if (artifact.type === "chart") return { type: "chart", artifact };
  if (artifact.type === "application") return { type: "application", artifact };
  return { type: "report", artifact };
}

export function buildChartOption(artifact: ChartArtifact) {
  const hasXY = artifact.data.some((d) => d.x != null || d.y != null);

  switch (artifact.chart_type) {
    case "pie":
      return {
        tooltip: { trigger: "item" as const },
        legend: { bottom: 0 },
        series: [{
          name: artifact.title,
          type: "pie",
          radius: ["38%", "68%"],
          data: artifact.data.map((d) => ({ name: d.name, value: d.value ?? 0 })),
        }],
      };

    case "funnel":
      return {
        tooltip: { trigger: "item" as const },
        legend: { bottom: 0 },
        series: [{
          name: artifact.title,
          type: "funnel",
          sort: "descending",
          data: artifact.data
            .filter((d) => d.value != null)
            .map((d) => ({ name: d.name, value: d.value ?? 0 })),
        }],
      };

    case "radar": {
      const radarDimensions = Array.from(new Set(artifact.data.map((d) => String(d.name))));
      const radarSeries = Array.from(new Set(artifact.data.map((d) => d.series || artifact.title)));
      return {
        tooltip: {},
        legend: { bottom: 0 },
        radar: {
          indicator: radarDimensions.map((name) => {
            const maxVal = Math.max(...artifact.data.filter((d) => d.name === name).map((d) => d.value ?? 0), 1);
            return { name, max: Math.ceil(maxVal * 1.2) };
          }),
        },
        series: radarSeries.map((group) => ({
          name: group,
          type: "radar",
          data: [{
            name: group,
            value: radarDimensions.map((dim) => {
              const item = artifact.data.find((d) => d.name === dim && (d.series || artifact.title) === group);
              return item?.value ?? 0;
            }),
          }],
        })),
      };
    }

    case "scatter":
      return buildXYChart(artifact, "scatter");

    case "bubble":
      return buildXYChart(artifact, "scatter", true);

    case "heatmap": {
      const xAxis = Array.from(new Set(artifact.data.map((d) => String(d.name))));
      const yAxis = Array.from(new Set(artifact.data.map((d) => d.series || artifact.title)));
      const heatData = artifact.data.map((d) => [
        xAxis.indexOf(String(d.name)),
        yAxis.indexOf(d.series || artifact.title),
        d.value ?? 0,
      ]);
      return {
        tooltip: {},
        grid: { left: 80, right: 20, top: 20, bottom: 80 },
        xAxis: { type: "category" as const, data: xAxis, axisLabel: { rotate: 45 } },
        yAxis: { type: "category" as const, data: yAxis },
        visualMap: { min: 0, max: Math.max(...heatData.map((d) => d[2]), 1), calculable: true, orient: "vertical", left: 0, bottom: 40 },
        series: [{ type: "heatmap", data: heatData }],
      };
    }

    case "line":
    case "bar":
    default: {
      const xAxis = Array.from(new Set(artifact.data.map((d) => String(d.name))));
      const groups = Array.from(new Set(artifact.data.map((d) => d.series || artifact.title)));
      const series = groups.map((group) => ({
        name: group,
        type: artifact.chart_type,
        smooth: artifact.chart_type === "line",
        data: xAxis.map((name) => {
          const item = artifact.data.find((e) => String(e.name) === name && (e.series || artifact.title) === group);
          return item?.value ?? 0;
        }),
      }));
      return {
        tooltip: { trigger: "axis" as const },
        legend: { bottom: 0 },
        grid: { left: 36, right: 18, top: 28, bottom: 56 },
        xAxis: { type: "category" as const, data: xAxis },
        yAxis: { type: "value" as const },
        series,
      };
    }
  }
}

function buildXYChart(artifact: ChartArtifact, chartType: "scatter", bubble = false) {
  const groups = Array.from(new Set(artifact.data.map((d) => d.series || artifact.title)));
  const series = groups.map((group) => ({
    name: group,
    type: chartType,
    data: artifact.data
      .filter((d) => (d.series || artifact.title) === group)
      .map((d) => {
        const point: number[] = [d.x ?? 0, d.y ?? 0];
        if (bubble) point.push(d.size ?? 10);
        return point;
      }),
  }));
  const allY = artifact.data.map((d) => d.y ?? 0);
  return {
    tooltip: {},
    legend: { bottom: 0 },
    grid: { left: 48, right: 24, top: 28, bottom: 56 },
    xAxis: { type: "value" as const },
    yAxis: { type: "value" as const },
    series: bubble
      ? series.map((s) => ({
          ...s,
          type: "scatter" as const,
          symbolSize: (val: number[]) => val[2] ?? 10,
        }))
      : series,
  };
}

export function chartTypeLabel(type: ChartArtifact["chart_type"]) {
  const labels: Record<string, string> = {
    pie: "饼图",
    line: "折线图",
    bar: "柱状图",
    scatter: "散点图",
    radar: "雷达图",
    funnel: "漏斗图",
    heatmap: "热力图",
    bubble: "气泡图",
  };
  return labels[type] || type;
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
