import re
from typing import Literal

from langchain_core.documents import Document

SEPARATOR_PRESETS: dict[str, list[str]] = {
    "general": ["\n\n", "\n", "。", ". ", "！", "! ", "？", "? ", "；", "; ", "，", ", ", " ", ""],
    "chinese": ["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
    "english": ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""],
}

_HEADING_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(#{1,6})\s+(.+)$"), "markdown"),
    (re.compile(r"^第[一二三四五六七八九十百千\d]+(章|节|条|部分|篇|编)\s*(.*)$"), "zh_chapter"),
    (re.compile(r"^[一二三四五六七八九十]+[、，]\s*(.*)$"), "zh_numbered"),
    (re.compile(r"^（[一二三四五六七八九十]+）\s*(.*)$"), "zh_bracketed"),
    (re.compile(r"^[一二三四五六七八九十]+[）)]\s*(.*)$"), "zh_paren"),
    (re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(.+)$"), "num_dotted"),
    (re.compile(r"^(\d+)\)\s+(.+)$"), "num_paren"),
]

_MAX_HEADING_LEN = 120
_SENTENCE_ENDS = re.compile(r"[。！？.!?]$")


def split_docs(
    docs: list[Document],
    chunk_size: int = 500,
    chunk_overlap: int = 100,
    strategy: Literal["fixed", "structure", "recursive"] = "fixed",
    separator_preset: Literal["general", "chinese", "english"] = "general",
) -> list[Document]:
    if not docs:
        return []

    if strategy == "structure":
        return _split_structure(docs, chunk_size, chunk_overlap)
    if strategy == "recursive":
        return _split_recursive(docs, chunk_size, chunk_overlap, separator_preset)
    return _split_fixed(docs, chunk_size, chunk_overlap)


# ---------------------------------------------------------------------------
# fixed
# ---------------------------------------------------------------------------

def _split_fixed(docs: list[Document], chunk_size: int, chunk_overlap: int) -> list[Document]:
    all_splits: list[Document] = []
    for doc in docs:
        text = doc.page_content
        if not text:
            continue
        chunks = _fixed_chunk_text(text, doc.metadata, chunk_size, chunk_overlap)
        all_splits.extend(chunks)
    return all_splits


def _fixed_chunk_text(text: str, metadata: dict, chunk_size: int, chunk_overlap: int) -> list[Document]:
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap 必须小于 chunk_size")

    chunks: list[Document] = []
    start = 0
    chunk_index = 0
    while start < len(text):
        end = start + chunk_size
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunk_meta = {**metadata, "chunk_index": chunk_index, "start_index": start, "end_index": end}
            chunks.append(Document(page_content=chunk_text, metadata=chunk_meta))
        start = max(end - chunk_overlap, 0)
        chunk_index += 1
    return chunks


# ---------------------------------------------------------------------------
# structure
# ---------------------------------------------------------------------------

def _split_structure(docs: list[Document], chunk_size: int, chunk_overlap: int) -> list[Document]:
    all_splits: list[Document] = []
    for doc in docs:
        text = doc.page_content
        if not text:
            continue
        headings = _extract_headings(text)
        sections = _split_by_headings(text, headings)
        for section_text, heading_path in sections:
            base_meta = {**doc.metadata, "heading_path": heading_path}
            if len(section_text) <= chunk_size:
                base_meta["chunk_index"] = 0
                base_meta["start_index"] = 0
                base_meta["end_index"] = len(section_text)
                all_splits.append(Document(page_content=section_text.strip(), metadata=base_meta))
            else:
                sub_chunks = _fixed_chunk_text(section_text, base_meta, chunk_size, chunk_overlap or 0)
                all_splits.extend(sub_chunks)
    return all_splits


def _extract_headings(text: str) -> list[dict]:
    """Extract heading lines with inferred hierarchy levels."""
    raw: list[dict] = []
    lines = text.split("\n")
    for line_idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line or len(line) > _MAX_HEADING_LEN:
            continue
        if _SENTENCE_ENDS.search(line):
            continue

        for pattern, style in _HEADING_PATTERNS:
            match = pattern.match(line)
            if not match:
                continue
            if style == "zh_chapter":
                title = match.group(2) or line
            elif style in ("zh_numbered", "zh_bracketed", "zh_paren"):
                title = match.group(1) or line
            else:
                title = match.group(2) or line
            if not title:
                title = line
            raw.append(
                {
                    "line_idx": line_idx,
                    "style": style,
                    "title": title.strip(),
                    "raw": line,
                    "marker": match.group(1) if style in ("markdown", "num_dotted", "num_paren") else "",
                    "level_hint": _infer_level(style, match),
                }
            )
            break

    if not raw:
        return []

    headings = _assign_levels(raw)
    return headings


def _infer_level(style: str, match: re.Match) -> int:
    """Return a relative level hint; higher number = deeper nesting."""
    if style == "markdown":
        return len(match.group(1))
    if style == "zh_chapter":
        return 1
    if style == "zh_numbered":
        return 2
    if style in ("zh_bracketed", "zh_paren"):
        return 3
    if style == "num_dotted":
        return match.group(1).count(".") + 1
    if style == "num_paren":
        return 3
    return 2


def _assign_levels(raw: list[dict]) -> list[dict]:
    """Assign absolute hierarchy levels.

    Markdown and num_dotted carry intrinsic levels from their syntax.
    Other styles are numbered by appearance order, creating a monotonic hierarchy.
    """
    if not raw:
        return raw

    # First pass: resolve intrinsic levels for markdown
    for item in raw:
        if item["style"] == "markdown":
            item["level"] = item["level_hint"]
        elif item["style"] == "num_dotted":
            dots = item["level_hint"] - 1
            # Single numbers like "1." default to level 4 (deeply nested),
            # multi-dot patterns like "1.1" use dots+2 as the level
            item["level"] = dots + 2 if dots > 0 else 4

    # Second pass: assign levels to remaining styles by appearance order
    style_level: dict[str, int] = {}
    next_level = 1
    for item in raw:
        style = item["style"]
        if "level" in item:
            continue
        if style not in style_level:
            style_level[style] = next_level
            next_level += 1
        item["level"] = style_level[style]

    return raw


def _split_by_headings(text: str, headings: list[dict]) -> list[tuple[str, list[str]]]:
    """Split text into sections by heading boundaries, each with its heading path."""
    if not headings:
        return [(text, [])]

    lines = text.split("\n")
    sections: list[tuple[str, list[str]]] = []
    stack: list[dict] = []

    section_start = 0

    for heading in headings:
        boundary = heading["line_idx"]
        if boundary <= section_start:
            _update_stack(stack, heading)
            continue

        section_text = "\n".join(lines[section_start:boundary])
        heading_path = [h["title"] for h in stack]
        if section_text.strip():
            sections.append((section_text, heading_path))

        _update_stack(stack, heading)
        section_start = boundary

    tail = "\n".join(lines[section_start:])
    heading_path = [h["title"] for h in stack]
    if tail.strip():
        sections.append((tail, heading_path))

    return sections


def _update_stack(stack: list[dict], heading: dict):
    while stack and stack[-1]["level"] >= heading["level"]:
        stack.pop()
    stack.append(heading)


# ---------------------------------------------------------------------------
# recursive
# ---------------------------------------------------------------------------

def _split_recursive(
    docs: list[Document],
    chunk_size: int,
    chunk_overlap: int,
    separator_preset: str,
) -> list[Document]:
    separators = SEPARATOR_PRESETS.get(separator_preset, SEPARATOR_PRESETS["general"])
    all_splits: list[Document] = []
    for doc in docs:
        text = doc.page_content
        if not text:
            continue
        chunks = _recursive_split_text(text, separators, 0, chunk_size, chunk_overlap, doc.metadata)
        all_splits.extend(chunks)
    return all_splits


def _recursive_split_text(
    text: str,
    separators: list[str],
    sep_idx: int,
    chunk_size: int,
    chunk_overlap: int,
    metadata: dict,
) -> list[Document]:
    if sep_idx >= len(separators):
        return _fixed_chunk_text(text, metadata, chunk_size, chunk_overlap)

    sep = separators[sep_idx]
    if not sep:
        return _fixed_chunk_text(text, metadata, chunk_size, chunk_overlap)

    splits = _split_by_separator(text, sep)
    result: list[Document] = []

    for piece in splits:
        if len(piece) <= chunk_size:
            if piece.strip():
                result.append(Document(page_content=piece.strip(), metadata={**metadata, "chunk_index": len(result)}))
        else:
            result.extend(
                _recursive_split_text(piece, separators, sep_idx + 1, chunk_size, 0, metadata)
            )

    if chunk_overlap > 0 and len(result) > 1:
        result = _apply_overlap(result, chunk_overlap)

    return result


def _split_by_separator(text: str, sep: str) -> list[str]:
    if sep == " ":
        return text.split(" ")
    parts = text.split(sep)
    result: list[str] = []
    for part in parts:
        if sep and part:
            result.append(part)
        elif not sep:
            result.append(part)
    if sep and result:
        for i in range(len(result) - 1):
            result[i] = result[i] + sep
    return result


def _apply_overlap(chunks: list[Document], overlap: int) -> list[Document]:
    if overlap <= 0:
        return chunks
    for i in range(len(chunks) - 1):
        current_text = chunks[i].page_content
        next_text = chunks[i + 1].page_content
        if len(next_text) > overlap:
            chunks[i] = Document(
                page_content=current_text + next_text[:overlap],
                metadata={**chunks[i].metadata},
            )
    return chunks
