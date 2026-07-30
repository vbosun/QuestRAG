import re
from typing import Literal

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

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
        chunks = _split_structure(docs, chunk_size, chunk_overlap)
    elif strategy == "recursive":
        chunks = _split_recursive(docs, chunk_size, chunk_overlap, separator_preset)
    else:
        chunks = _split_fixed(docs, chunk_size, chunk_overlap)

    for c in chunks:
        c.metadata["strategy"] = strategy
        c.metadata["separator_preset"] = separator_preset
    return chunks


# ---------------------------------------------------------------------------
# fixed
# ---------------------------------------------------------------------------

_DEFAULT_SEPARATORS = ["\n\n", "\n", "。", ". ", "！", "! ", "？", "? ", "；", "; ", "，", ", ", " ", ""]


def _split_fixed(docs: list[Document], chunk_size: int, chunk_overlap: int) -> list[Document]:
    return _split_with_langchain(docs, chunk_size, chunk_overlap, _DEFAULT_SEPARATORS)


def _split_with_langchain(
    docs: list[Document],
    chunk_size: int,
    chunk_overlap: int,
    separators: list[str],
) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=separators,
        keep_separator=True,
        strip_whitespace=False,
    )
    all_splits: list[Document] = []
    for doc in docs:
        text = doc.page_content
        if not text:
            continue
        for chunk_text in splitter.split_text(text):
            all_splits.append(Document(
                page_content=chunk_text.strip(),
                metadata={**doc.metadata, "chunk_index": len(all_splits)},
            ))
    return all_splits


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
            chunks = _split_with_langchain([doc], chunk_size, chunk_overlap or 0, _DEFAULT_SEPARATORS)
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
        dots = match.group(1).count(".")
        return dots + 1 if dots > 0 else 7  # single-number patterns go deepest
    if style == "num_paren":
        return 7
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
        elif item["style"] == "num_dotted" and hint > 1 and hint < 7:
            # "1.1" → level 2, "1.1.1" → level 3, etc.
            item["level"] = hint + 1
        elif item["style"] == "num_dotted":
            # Single numbers like "1." — non-intrinsic, place below markdown
            item["level"] = 7
        elif item["style"] == "num_paren":
            item["level"] = 7

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
    if len(text) <= chunk_size:
        chunks.append(_make_chunk(text, heading_path, base_metadata, chunks))
        return

    # 超限拆分时，提取首行标题作为前缀，拼回每个子块，避免标题孤立
    heading_prefix = ""
    body = text
    first_line = text.split("\n", 1)[0].strip()
    if first_line and any(p.match(first_line) for p, _ in _HEADING_PATTERNS):
        heading_prefix = first_line
        body = text[len(first_line):].strip()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap or 0,
        separators=_DEFAULT_SEPARATORS,
        keep_separator=True,
        strip_whitespace=False,
    )
    for sub_text in splitter.split_text(body):
        content = f"{heading_prefix}\n{sub_text.strip()}" if heading_prefix else sub_text.strip()
        if content.strip():
            chunks.append(_make_chunk(content, heading_path, base_metadata, chunks))


def _make_chunk(text: str, heading_path: list[str], base_metadata: dict, chunks: list[Document]) -> Document:
    return Document(
        page_content=text,
        metadata={**base_metadata, "heading_path": heading_path, "chunk_index": len(chunks)},
    )


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
    return _split_with_langchain(docs, chunk_size, chunk_overlap, separators)
