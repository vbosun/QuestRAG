"""
RAG 检索权限过滤：构造权限过滤条件，取用户 rag_scopes 与请求范围的交集。
"""
from pydantic import BaseModel

from quest_rag.auth.schemas import CurrentUser


class RetrievalPermissionFilter(BaseModel):
    scope_codes: list[str]
    doc_ids: list[str] | None = None
    visibility: list[str] | None = None
    security_levels: list[str] | None = None

    @property
    def is_empty(self) -> bool:
        return not self.scope_codes


def build_retrieval_permission_filter(
    current_user: CurrentUser,
    requested_scopes: list[str] | None = None,
    requested_doc_ids: list[str] | None = None,
) -> RetrievalPermissionFilter:
    allowed_scopes = set(current_user.rag_scopes)
    if not allowed_scopes:
        return RetrievalPermissionFilter(scope_codes=[])

    requested = set(requested_scopes) if requested_scopes else allowed_scopes
    effective_scopes = sorted(allowed_scopes & requested)

    # doc_id 交集（第一阶段不做，但保留接口）
    effective_doc_ids = None
    if requested_doc_ids:
        effective_doc_ids = sorted(requested_doc_ids)

    return RetrievalPermissionFilter(
        scope_codes=effective_scopes,
        doc_ids=effective_doc_ids,
    )
