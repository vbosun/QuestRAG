from dataclasses import asdict, dataclass, field
from contextvars import ContextVar
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


_citation_sources: ContextVar[list[CitationSource] | None] = ContextVar("citation_sources", default=None)
_citation_lock = RLock()


def _current_sources() -> list[CitationSource]:
    sources = _citation_sources.get()
    if sources is None:
        sources = []
        _citation_sources.set(sources)
    return sources


def reset_citations() -> None:
    # A fresh list is copied with the request context into tool threads; another
    # request cannot clear or read it. Never mutate a process-global list here.
    _citation_sources.set([])


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
        sources = _current_sources()
        for source in sources:
            if source.ref_id == ref_id:
                return source.label

        label = str(len(sources) + 1)
        sources.append(
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
        return [asdict(source) for source in _current_sources()]
