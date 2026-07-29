import type { Artifact, MessagePart } from "./types";

const ARTIFACT_BLOCK_RE = /```questrag-artifact\s*([\s\S]*?)```/g;

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

function parseArtifact(value: string): Artifact | null {
  try {
    const parsed = JSON.parse(value.trim());
    if (parsed?.type === "chart" && Array.isArray(parsed.data)) {
      return parsed;
    }
    if (parsed?.type === "report" && typeof parsed.content === "string") {
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
