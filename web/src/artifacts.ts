import type { Artifact, MessagePart } from "./types";

const ARTIFACT_BLOCK_RE = /```\s*questrag-artifact\s*([\s\S]*?)```/g;
const ARTIFACT_FENCE_START_RE = /```\s*questrag-artifact\s*/g;
const ARTIFACT_FENCE_PREFIX = "```questrag-artifact";

export function parseMessageParts(raw: string): MessagePart[] {
  const parts: MessagePart[] = [];
  let cursor = 0;

  for (const match of raw.matchAll(ARTIFACT_BLOCK_RE)) {
    const index = match.index ?? 0;
    const before = raw.slice(cursor, index);
    if (before) {
      parts.push({ type: "markdown", content: before });
    }

    const artifact = parseArtifact(match[1]);
    if (artifact?.type === "chart") {
      parts.push({ type: "chart", artifact });
    } else if (artifact?.type === "report") {
      parts.push({ type: "report", artifact });
    } else if (artifact?.type === "application") {
      parts.push({ type: "application", artifact });
    } else {
      parts.push({ type: "markdown", content: match[0] });
    }

    cursor = index + match[0].length;
  }

  const tail = raw.slice(cursor);
  if (tail) {
    parts.push({ type: "markdown", content: tail });
  }

  return mergeMarkdownParts(parts);
}

export function parseStreamingMessageParts(raw: string): { parts: MessagePart[]; bufferingArtifact: boolean } {
  const openFenceIndex = findOpenArtifactFence(raw);
  if (openFenceIndex < 0) {
    const prefixIndex = findTrailingArtifactFencePrefix(raw);
    if (prefixIndex >= 0) {
      return {
        parts: parseMessageParts(raw.slice(0, prefixIndex)),
        bufferingArtifact: true,
      };
    }
    return { parts: parseMessageParts(raw), bufferingArtifact: false };
  }
  return {
    parts: parseMessageParts(raw.slice(0, openFenceIndex)),
    bufferingArtifact: true,
  };
}

function findTrailingArtifactFencePrefix(raw: string) {
  const normalized = (value: string) => value.replace(/\s+/g, "");
  const maxLength = Math.min(raw.length, ARTIFACT_FENCE_PREFIX.length + 8);
  for (let length = maxLength; length >= 3; length -= 1) {
    const start = raw.length - length;
    const suffix = raw.slice(start);
    const compact = normalized(suffix).toLowerCase();
    if (ARTIFACT_FENCE_PREFIX.startsWith(compact) && isOpeningFencePosition(raw, start)) {
      return start;
    }
  }
  return -1;
}

function isOpeningFencePosition(raw: string, index: number) {
  const before = raw.slice(0, index);
  const fenceCount = before.match(/```/g)?.length || 0;
  return fenceCount % 2 === 0;
}

function findOpenArtifactFence(raw: string) {
  ARTIFACT_FENCE_START_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = ARTIFACT_FENCE_START_RE.exec(raw)) !== null) {
    const closeIndex = raw.indexOf("```", ARTIFACT_FENCE_START_RE.lastIndex);
    if (closeIndex < 0) return match.index;
    ARTIFACT_FENCE_START_RE.lastIndex = closeIndex + 3;
  }
  return -1;
}

function parseArtifact(value: string): Artifact | null {
  try {
    const parsed = JSON.parse(value.trim());
    if (parsed?.type === "chart" && Array.isArray(parsed.data)) {
      return parsed;
    }
    if (parsed?.type === "report" && typeof parsed.content === "string") {
      return parsed;
    }
    if (parsed?.type === "application" && typeof parsed.case_id === "string" && typeof parsed.title === "string") {
      return parsed;
    }
  } catch {
    return null;
  }
  return null;
}

function mergeMarkdownParts(parts: MessagePart[]): MessagePart[] {
  const merged: MessagePart[] = [];
  for (const part of parts) {
    const last = merged[merged.length - 1];
    if (part.type === "markdown" && last?.type === "markdown") {
      last.content += part.content;
    } else {
      merged.push(part);
    }
  }
  return merged.length ? merged : [{ type: "markdown", content: "" }];
}

export function appendMarkdownToParts(parts: MessagePart[], text: string): MessagePart[] {
  const next = [...parts];
  const last = next[next.length - 1];
  if (last?.type === "markdown") {
    next[next.length - 1] = { ...last, content: last.content + text };
  } else {
    next.push({ type: "markdown", content: text });
  }
  return next;
}
