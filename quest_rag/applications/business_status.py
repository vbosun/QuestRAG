"""Read authoritative business receipts with a per-case capability, never admin credentials."""
import json
from datetime import datetime, timezone

import httpx

from quest_rag.applications import store
from quest_rag.core.config import MOCK_BUSINESS_BASE_URL

LABELS = {"PENDING": "待审批", "APPROVED": "已通过", "REJECTED": "已驳回"}


def lookup(case: dict) -> str:
    case_id = str(case["id"])
    missing = {"case_id": case_id, "source": "独立模拟业务系统", "status": "NO_LINKED_RECEIPT",
               "message": "暂未查到已关联的业务回执，不能判断审批进度。未提交的申请可继续填写；旧申请请凭原回执到独立业务系统查询。"}
    link = store.get_business_link(case_id)
    if not link:
        return json.dumps(missing, ensure_ascii=False)
    try:
        # Fixed configured service origin; neither model arguments nor page URLs choose the target.
        with httpx.Client(base_url=MOCK_BUSINESS_BASE_URL or "http://127.0.0.1:8020", timeout=5, trust_env=False, follow_redirects=False) as client:
            response = client.post("/business/api/case-status", headers={"X-Business-Request": "1"},
                                   json={"case_id": case_id, "token": link["query_token"]})
        if response.status_code == 404:
            return json.dumps(missing, ensure_ascii=False)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Invalid business receipt")
        expected_business = case["business_code"].replace("_", "-")
        if data.get("case_id") != case_id or data.get("business") != expected_business or data.get("status") not in LABELS:
            raise ValueError("Mismatched business receipt")
        status = data["status"]
        result = {"case_id": case_id, "source": "独立模拟业务系统", "status": status, "status_label": LABELS[status],
                  "application_no": data["number"], "business_name": data["business_name"],
                  "submitted_at": data["created_at"], "reviewed_at": data.get("reviewed_at"), "review_comment": data.get("comment") or "",
                  "checked_at": datetime.now(timezone.utc).isoformat(),
                  "materials": [{key: item.get(key) for key in ('key', 'name', 'size_bytes', 'status', 'received_at')}
                                for item in data.get('materials', []) if isinstance(item, dict)],
                  "guidance": "材料接收记录以本结果为准。申请已提交，关闭申请窗口不影响审批；不要依据本地草稿、附件表或页面连接状态提示补传、待同步或重新打开页面。材料已接收不表示审核通过。",
                  "next_action": {"PENDING": "等待审批人员核对信息与材料。", "APPROVED": "本次模拟申请已审批通过。", "REJECTED": "请查看驳回意见，准备好材料后从业务首页重新申请。"}[status]}
        return json.dumps(result, ensure_ascii=False)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        # Never include upstream response bodies, URLs or capabilities in model output.
        return json.dumps({"case_id": case_id, "source": "独立模拟业务系统", "status": "UNAVAILABLE",
                           "message": "业务系统暂时无法查询，当前审批进度未确认，请稍后重试。不能依据草稿状态推断审批结果。"}, ensure_ascii=False)
