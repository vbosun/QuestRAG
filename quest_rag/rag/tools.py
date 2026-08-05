import json
import re
import uuid

from langchain.tools import tool

from quest_rag.core.config import get_retrieval_config
from quest_rag.rag.citations import register_citation
from quest_rag.rag.document_retriever import search
from quest_rag.rag.job_retriever import search_jobs
from quest_rag.rag.result_validator import validate_search_result
from quest_rag.rag.retrieval_permissions import build_retrieval_permission_filter
from quest_rag.rag.storage import get_all_docs, get_doc_by_name
from quest_rag.rag.tool_registry import assert_tool_permission, current_conversation_ctx, current_user_ctx
from quest_rag.rag.trace import append_tool_trace
from quest_rag.schemas.schemas import (
    ChartArtifact,
    ChartToolInput,
    DocMetadata,
    JobSearchToolInput,
)
from quest_rag.social_security.schemas import SocialSecuritySearchToolInput
from quest_rag.social_security.service import format_social_security_result
from quest_rag.subsidy.schemas import SubsidyCalculateToolInput, SubsidyMatchToolInput
from quest_rag.subsidy.service import calculate_for_user, match_for_user
from quest_rag.chat_memory.store import insert_tool_memory


@tool
def retrieve_context(query: str) -> str:
    """ 根据查询目标检索文档,返回查询结果 """
    user = current_user_ctx.get()
    if user is not None:
        assert_tool_permission(user, "retrieve_context")
    cfg = get_retrieval_config()

    permission_filter = None
    if user is not None:
        permission_filter = build_retrieval_permission_filter(user)

    docs = search(query, cfg["top_k"], permission_filter=permission_filter)

    results = validate_search_result(docs)
    append_tool_trace(
        {
            "tool_name": "retrieve_context",
            "target": "evaluation_documents",
            "query": query,
            "contexts": [
                {
                    "text": doc.page_content,
                    "metadata": doc.metadata or {},
                }
                for doc in results
            ],
        }
    )

    serialized_parts = []
    for doc in results:
        metadata = doc.metadata or {}
        chunk_id = metadata.get("chunk_id") or metadata.get("id") or "unknown_chunk"
        doc_id = metadata.get("doc_id") or metadata.get("source") or "unknown_document"
        ref_id = f"{doc_id}#{chunk_id}"
        label = register_citation(
            ref_id=ref_id,
            source_type="knowledge",
            title=metadata.get("filename") or metadata.get("source") or str(doc_id),
            snippet=doc.page_content[:500],
            metadata={
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "filename": metadata.get("filename"),
                "source": metadata.get("source"),
                "page": metadata.get("page"),
                "page_label": metadata.get("page_label"),
                "chunk_index": metadata.get("chunk_index"),
            },
        )
        serialized_parts.append(
            "\n".join(
                [
                    f"引用编号: 【{label}】",
                    f"来源文档: {metadata.get('filename') or metadata.get('source', '未知')}",
                    f"片段位置: chunk_id={chunk_id}, page={metadata.get('page', '无')}, chunk_index={metadata.get('chunk_index', '无')}",
                    f"内容: {doc.page_content}",
                ]
            )
        )

    serialized = "\n\n".join(serialized_parts)
    print(f"""
          query: {query}
          serialized: {serialized}

""")
    return serialized


@tool
def get_document_list(name: str | None) -> list[DocMetadata] | None:
    """
    获取文档信息列表。

    如果不提供名称，则返回所有文档的元数据列表；
    如果提供名称，则返回文档名称中包含该字符串的文档信息（模糊匹配）。
    """
    user = current_user_ctx.get()
    if user is not None:
        assert_tool_permission(user, "get_document_list")

    if not name:
        docs = get_all_docs()
    else:
        docs = get_doc_by_name(name)
    if user is None:
        return docs
    allowed_scopes = set(user.rag_scopes)
    if not allowed_scopes:
        return []
    return [doc for doc in docs if doc.scope_code in allowed_scopes]


@tool(args_schema=JobSearchToolInput)
def retrieve_jobs(query: str, top_k: int | None = None) -> str:
    """
    检索公开岗位数据，最多返回 10 条。

    适合回答岗位推荐、职位查询、薪资/地点/学历/经验匹配等问题。
    """
    user = current_user_ctx.get()
    if user is not None:
        assert_tool_permission(user, "retrieve_jobs")

    if top_k is None:
        top_k = get_retrieval_config()["top_k"]
    jobs = search_jobs(query, top_k)
    append_tool_trace(
        {
            "tool_name": "retrieve_jobs",
            "target": "jobs",
            "query": query,
            "top_k": top_k,
            "contexts": [
                {
                    "text": format_job_result(job),
                    "metadata": {
                        "source_type": "job",
                        "job_id": job.get("id"),
                        "title": job.get("title"),
                        "company": job.get("company"),
                    },
                }
                for job in jobs
            ],
        }
    )
    if not jobs:
        return "未检索到匹配岗位。"

    return "\n\n".join(
        format_job_result(job)
        for job in jobs
    )


@tool(args_schema=ChartToolInput)
def create_chart_artifact(
    chart_type: str,
    title: str,
    data: list[dict],
    description: str | None = None,
    x_field: str = "name",
    y_field: str = "value",
    series_field: str | None = None,
    source_note: str | None = None,
) -> str:
    """
    生成前端可渲染的图表资产。仅当回答中确实有可量化数据时调用。

    按数据类型选择合适的 chart_type：
    - pie：占比/构成分析（如部门预算占比、学历分布）
    - line：时间趋势/连续变化（如月度销售额、温度变化）
    - bar：数值对比/排名（如各省 GDP 对比、考试成绩排名）
    - scatter：两个数值变量的相关性/分布（如身高与体重关系）
    - radar：多维度综合评价（如各产品的性能/价格/外观评分）
    - funnel：逐层递减的转化/层级数据（如招聘漏斗、销售转化）
    - heatmap：两个维度的交叉强度（如不同城市×月份的销量热度）
    - bubble：三维数据关系（如国家 GDP×人口×人均收入，size=人口）

    数据按 chart_type 填写：
    - pie/funnel：每项填 name + value
    - line/bar/radar：每项填 name + value，有多条线/多组柱时用 series 字段区分
    - scatter：每项填 x + y（两个数值坐标），多个系列用 series 区分
    - bubble：每项填 x + y + size，多个系列用 series 区分
    - heatmap：每项填 name（X轴维度）+ series（Y轴维度）+ value（强度值）

    注意：x_field/y_field/series_field 一般保持默认即可，无需修改。
    """
    artifact = ChartArtifact(
        id=f"chart_{uuid.uuid4().hex[:12]}",
        chart_type=chart_type,
        title=title,
        description=description,
        data=data,
        encoding={
            "x": x_field,
            "y": y_field,
            "series": series_field,
        },
        download={
            "filename": f"{sanitize_filename(title)}.png",
        },
        source_note=source_note or "数据由本次回答整理生成，请结合原始资料核对。",
    )
    payload = artifact.model_dump(mode="json")
    return (
        "请在回答中把下面这个图表资产原样放入独立的 ```questrag-artifact 代码块，"
        "并在图表前后用 Markdown 解释其含义。\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]+', "_", value).strip(" ._")
    return cleaned[:60] or "chart"


# ── 工具列表 ──
@tool(args_schema=SocialSecuritySearchToolInput)
def social_security_search(
    query_type: str = "summary",
    insurance_type: str | None = None,
    start_month: str | None = None,
    end_month: str | None = None,
    limit: int = 12,
) -> str:
    """查询当前登录用户本人的模拟社保概要、缴费记录或账户余额。"""
    user = current_user_ctx.get()
    if user is None:
        return "社保查询需要登录用户上下文。"
    assert_tool_permission(user, "social_security_search")
    result = format_social_security_result(
        user,
        query_type=query_type,
        insurance_type=insurance_type,
        start_month=start_month,
        end_month=end_month,
        limit=limit,
    )
    remember_tool_result(
        user.id,
        "social_security_search",
        "social_security_summary",
        {
            "query_type": query_type,
            "insurance_type": insurance_type,
            "start_month": start_month,
            "end_month": end_month,
            "summary_text": result[:1200],
        },
        input_summary=f"{query_type}/{insurance_type or 'all'}",
        output_summary=result[:300],
    )
    return result


@tool(args_schema=SubsidyMatchToolInput)
def subsidy_match(user_description: str, extracted_facts: dict | None = None, top_k: int = 5) -> str:
    """根据用户描述、本人画像和模拟社保数据匹配候选补贴，并返回缺失字段。"""
    user = current_user_ctx.get()
    if user is None:
        return "补贴匹配需要登录用户上下文。"
    assert_tool_permission(user, "subsidy_match")
    matches = match_for_user(user, user_description, extracted_facts or {}, top_k)
    payload = [item.model_dump() for item in matches]
    remember_tool_result(
        user.id,
        "subsidy_match",
        "subsidy_candidates",
        {"user_description": user_description, "candidates": payload},
        input_summary=user_description[:300],
        output_summary="；".join(item.policy_name for item in matches[:3]),
    )
    return json.dumps(payload, ensure_ascii=False, default=str)


@tool(args_schema=SubsidyCalculateToolInput)
def subsidy_calculate(policy_id: str, user_inputs: dict | None = None) -> str:
    """对指定补贴执行确定性规则测算，返回资格、金额、计算过程、材料和流程。"""
    user = current_user_ctx.get()
    if user is None:
        return "补贴测算需要登录用户上下文。"
    assert_tool_permission(user, "subsidy_calculate")
    result = calculate_for_user(user, policy_id, user_inputs or {})
    payload = result.model_dump()
    remember_tool_result(
        user.id,
        "subsidy_calculate",
        "subsidy_calculation",
        payload,
        input_summary=f"{policy_id}: {json.dumps(user_inputs or {}, ensure_ascii=False)[:240]}",
        output_summary=f"{result.policy_name}: {result.status}, {result.estimated_amount or '-'}{result.amount_unit}",
    )
    return json.dumps(payload, ensure_ascii=False, default=str)


def remember_tool_result(
    user_id: int,
    tool_name: str,
    memory_type: str,
    facts: dict,
    input_summary: str | None = None,
    output_summary: str | None = None,
) -> None:
    conversation_id = current_conversation_ctx.get()
    if not conversation_id:
        return
    insert_tool_memory(
        user_id=user_id,
        conversation_id=conversation_id,
        tool_name=tool_name,
        memory_type=memory_type,
        facts=facts,
        input_summary=input_summary,
        output_summary=output_summary,
    )


tools = [
    retrieve_context,
    get_document_list,
    retrieve_jobs,
    create_chart_artifact,
    social_security_search,
    subsidy_match,
    subsidy_calculate,
]


def format_job_result(job: dict) -> str:
    job_id = job.get("id") or "unknown_job"
    label = register_citation(
        ref_id=str(job_id),
        source_type="job",
        title=job.get("title") or "未命名岗位",
        snippet=job.get("content")
        or "；".join(
            str(value)
            for value in [
                job.get("title"),
                job.get("company"),
                job.get("address"),
                job.get("salary"),
            ]
            if value
        ),
        metadata={
            "job_id": job_id,
            "company": job.get("company"),
            "address": job.get("address"),
            "salary": job.get("salary"),
            "education": job.get("education"),
            "experience": job.get("experience"),
            "industry": job.get("industry"),
            "category": job.get("category"),
            "headcount": job.get("headcount"),
            "updated": job.get("updated"),
            "source": job.get("source"),
            "score": job.get("score"),
        },
        url=job.get("url"),
    )
    return "\n".join(
        [
            f"引用编号: 【{label}】",
            f"岗位: {job.get('title') or '未命名岗位'}",
            f"单位: {job.get('company') or '未知'}",
            f"地点: {job.get('address') or '未知'}",
            f"薪资: {job.get('salary') or '未知'}",
            f"岗位类别: {job.get('category') or '未知'}",
            f"招聘人数: {job.get('headcount') or '未知'}",
            f"经验: {job.get('experience') or '未知'}",
            f"学历: {job.get('education') or '未知'}",
            f"来源: {job.get('source') or '未知'}",
            f"匹配分: {job.get('score', 0):.3f}",
        ]
    )
