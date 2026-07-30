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
    (re.compile(r"^\([一二三四五六七八九十]+\)\s*(.*)$"), "zh_bracketed"),
    (re.compile(r"^[一二三四五六七八九十]+[）)]\s*(.*)$"), "zh_paren"),
    (re.compile(r"^(\d+(?:\.\d+)*)\.\s*(.+)$"), "num_dotted"),
    (re.compile(r"^(\d+)\)\s*(.+)$"), "num_paren"),
]

_MAX_HEADING_LEN = 120
_MAX_HEADING_DEPTH = 4
_MIN_STANDALONE_CHUNK = 80  # 子块至少 80 字才允许独立，避免产生碎片
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
        if not headings:
            chunks = _fixed_chunk_text(text, doc.metadata, chunk_size, chunk_overlap or 0)
            all_splits.extend(chunks)
        else:
            chunks = _split_by_tree(text, headings, chunk_size, chunk_overlap, doc.metadata)
            all_splits.extend(chunks)
    return all_splits


def _extract_headings(text: str) -> list[dict]:
    """Extract heading lines with inferred hierarchy levels."""
    raw: list[dict] = []
    lines = text.split("\n")
    for line_idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line or len(line) > _MAX_HEADING_LEN:
            continue

        for pattern, style in _HEADING_PATTERNS:
            match = pattern.match(line)
            if not match:
                continue
            # 模式命中后，额外检查：如果不是标题型样式且以句末标点结尾，可能是正文
            if style not in ("zh_numbered", "zh_bracketed", "zh_paren", "num_dotted", "num_paren", "markdown"):
                if _SENTENCE_ENDS.search(line):
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

    Markdown headings carry intrinsic levels from # count.
    Multi-dot numbered headings (1.1, 2.3.1) carry intrinsic levels.
    All other styles are numbered by first-appearance order.
    Single-number patterns (1. 2.) are treated as non-intrinsic since
    their nesting depth varies by document context.
    """
    if not raw:
        return raw

    for item in raw:
        hint = item["level_hint"]
        if item["style"] == "markdown":
            item["level"] = hint
        elif item["style"] == "num_dotted" and hint > 1:
            # "1.1" → level 2, "1.1.1" → level 3, etc.
            item["level"] = hint + 1
        elif item["style"] == "num_dotted":
            # Single numbers like "1." — non-intrinsic, will be handled below
            pass

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


def _split_by_tree(
    text: str,
    headings: list[dict],
    chunk_size: int,
    chunk_overlap: int,
    base_metadata: dict,
) -> list[Document]:
    """Split text by heading tree. Only drills into sub-headings when the parent
    section's total text exceeds chunk_size. Otherwise keeps the section intact."""
    lines = text.split("\n")
    total_lines = len(lines)
    chunks: list[Document] = []
    _split_subtree(
        text_lines=lines,
        sub_headings=headings,
        start_line=0,
        end_line=total_lines,
        parent_path=[],
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        base_metadata=base_metadata,
        chunks=chunks,
    )
    return chunks


def _split_subtree(
    *,
    text_lines: list[str],
    sub_headings: list[dict],
    start_line: int,
    end_line: int,
    parent_path: list[str],
    chunk_size: int,
    chunk_overlap: int,
    base_metadata: dict,
    chunks: list[Document],
):
    """Recursively process a section of text [start_line, end_line) with its headings."""
    # Gather direct children: the highest-level (lowest level number) headings
    if not sub_headings:
        section_text = "\n".join(text_lines[start_line:end_line]).strip()
        if section_text:
            _emit_chunk(section_text, parent_path, base_metadata, chunk_size, chunk_overlap, chunks)
        return

    min_level = min(h["level"] for h in sub_headings)
    # Extract headings that are at the minimum level within this subtree
    direct_children: list[dict] = []
    remaining: list[dict] = []
    for h in sub_headings:
        if h["level"] == min_level:
            direct_children.append(h)
        else:
            remaining.append(h)

    # Text before the first direct child heading
    first_child_line = direct_children[0]["line_idx"]
    if first_child_line > start_line:
        preamble = "\n".join(text_lines[start_line:first_child_line]).strip()
        if preamble:
            _emit_chunk(preamble, parent_path, base_metadata, chunk_size, chunk_overlap, chunks)

    # Process each direct child
    for i, child in enumerate(direct_children):
        child_start = child["line_idx"]
        # Find where this child's content ends
        if i + 1 < len(direct_children):
            child_end = direct_children[i + 1]["line_idx"]
        else:
            child_end = end_line

        child_path = (parent_path + [child["title"]])[-_MAX_HEADING_DEPTH:]
        section_text = "\n".join(text_lines[child_start:child_end]).strip()
        total_len = len(section_text)

        if total_len <= chunk_size:
            # Check if sub-headings would produce meaningful standalone chunks
            child_sub = [
                h for h in remaining
                if h["line_idx"] >= child_start
                and (i + 1 >= len(direct_children) or h["line_idx"] < direct_children[i + 1]["line_idx"])
            ]
            if child_sub and _can_split_meaningfully(text_lines, child_start, child_end, child_sub):
                _split_subtree(
                    text_lines=text_lines,
                    sub_headings=child_sub,
                    start_line=child_start,
                    end_line=child_end,
                    parent_path=child_path,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    base_metadata=base_metadata,
                    chunks=chunks,
                )
                continue
            _emit_chunk(section_text, child_path, base_metadata, chunk_size, chunk_overlap, chunks)
            continue

        # Exceeds limit — drill into sub-headings
        child_sub_headings = [
            h for h in remaining
            if h["line_idx"] >= child_start
            and (i + 1 >= len(direct_children) or h["line_idx"] < direct_children[i + 1]["line_idx"])
        ]
        if child_sub_headings:
            _split_subtree(
                text_lines=text_lines,
                sub_headings=child_sub_headings,
                start_line=child_start,
                end_line=child_end,
                parent_path=child_path,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                base_metadata=base_metadata,
                chunks=chunks,
            )
        else:
            # No sub-headings to help, fall back to fixed-length
            _emit_chunk(section_text, child_path, base_metadata, chunk_size, chunk_overlap, chunks)


def _can_split_meaningfully(
    text_lines: list[str],
    start_line: int,
    end_line: int,
    sub_headings: list[dict],
) -> bool:
    """Check if splitting by sub-headings produces chunks of at least _MIN_STANDALONE_CHUNK chars each."""
    if not sub_headings:
        return False
    min_level = min(h["level"] for h in sub_headings)
    direct = [h for h in sub_headings if h["level"] == min_level]
    if not direct:
        return False
    for i, h in enumerate(direct):
        seg_start = h["line_idx"]
        seg_end = direct[i + 1]["line_idx"] if i + 1 < len(direct) else end_line
        if len("\n".join(text_lines[seg_start:seg_end]).strip()) < _MIN_STANDALONE_CHUNK:
            return False
    return True


def _emit_chunk(
    text: str,
    heading_path: list[str],
    base_metadata: dict,
    chunk_size: int,
    chunk_overlap: int,
    chunks: list[Document],
):
    """Emit text as chunk(s), using fixed-length splitting if it exceeds chunk_size."""
    if len(text) <= chunk_size:
        chunks.append(Document(
            page_content=text,
            metadata={**base_metadata, "heading_path": heading_path, "chunk_index": len(chunks)},
        ))
    else:
        for sub in _fixed_chunk_text(text, {**base_metadata, "heading_path": heading_path}, chunk_size, chunk_overlap or 0):
            chunks.append(sub)


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
