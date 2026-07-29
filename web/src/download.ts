import type { MessagePart } from "./types";

export function downloadText(filename: string, content: string, mime = "text/markdown") {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function messagePartsToMarkdown(parts: MessagePart[]) {
  return parts
    .map((part) => {
      if (part.type === "markdown") return part.content;
      if (part.type === "chart") {
        return `\n\n### ${part.artifact.title}\n\n${part.artifact.description || ""}\n\n`;
      }
      return `\n\n### ${part.artifact.title}\n\n${part.artifact.content}\n\n`;
    })
    .join("")
    .trim();
}
