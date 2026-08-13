import json
import re
from typing import Any

from quest_rag.schemas.schemas import ChartArtifact

ARTIFACT_BLOCK_RE = re.compile(r"```\s*questrag-artifact\s*([\s\S]*?)```")


def parse_message_parts(raw: str) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    cursor = 0

    for match in ARTIFACT_BLOCK_RE.finditer(raw or ""):
        before = raw[cursor:match.start()]
        if before:
            parts.append({"type": "markdown", "content": before})

        artifact = parse_artifact(match.group(1))
        if artifact and artifact.get("type") in {"chart", "report", "application"}:
            parts.append({"type": artifact["type"], "artifact": artifact})
        else:
            parts.append({"type": "markdown", "content": match.group(0)})

        cursor = match.end()

    tail = (raw or "")[cursor:]
    if tail:
        parts.append({"type": "markdown", "content": tail})

    return merge_markdown_parts(parts)


def normalize_message_parts(raw: str, parts: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not raw:
        return parts or []
    if not parts:
        return parse_message_parts(raw)
    if len(parts) == 1 and parts[0].get("type") == "markdown" and ARTIFACT_BLOCK_RE.search(raw):
        return parse_message_parts(raw)
    return parts


def parse_artifact(value: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(value.strip())
    except json.JSONDecodeError:
        return None

    if parsed.get("type") == "chart" and isinstance(parsed.get("data"), list):
        try:
            return _dump_model(ChartArtifact(**parsed))
        except Exception:
            return None
    if parsed.get("type") == "report" and isinstance(parsed.get("content"), str):
        return parsed
    if (
        parsed.get("type") == "application"
        and isinstance(parsed.get("case_id"), str)
        and isinstance(parsed.get("title"), str)
    ):
        return parsed
    return None


def merge_markdown_parts(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for part in parts:
        last = merged[-1] if merged else None
        if part.get("type") == "markdown" and last and last.get("type") == "markdown":
            last["content"] = f"{last.get('content', '')}{part.get('content', '')}"
        else:
            merged.append(part)
    return merged or [{"type": "markdown", "content": ""}]


def _dump_model(model) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
