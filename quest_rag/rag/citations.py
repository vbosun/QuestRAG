from dataclasses import asdict, dataclass, field
from threading import RLock
from typing import Any


@dataclass
class CitationSource:
    label: str
    ref_id: str
    source_type: str
    title: str
    snippet: str
    metadata: dict[str, Any] = field(default_factory=dict)
    url: str | None = None


_citation_sources: list[CitationSource] = []
_citation_lock = RLock()


def reset_citations() -> None:
    with _citation_lock:
        _citation_sources.clear()


def register_citation(
    *,
    ref_id: str,
    source_type: str,
    title: str,
    snippet: str,
    metadata: dict[str, Any] | None = None,
    url: str | None = None,
) -> str:
    with _citation_lock:
        for source in _citation_sources:
            if source.ref_id == ref_id:
                return source.label

        label = str(len(_citation_sources) + 1)
        _citation_sources.append(
            CitationSource(
                label=label,
                ref_id=ref_id,
                source_type=source_type,
                title=title,
                snippet=snippet.strip(),
                metadata=metadata or {},
                url=url,
            )
        )
        return label


def get_citations() -> list[dict[str, Any]]:
    with _citation_lock:
        return [asdict(source) for source in _citation_sources]
