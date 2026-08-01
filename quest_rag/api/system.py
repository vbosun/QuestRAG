from fastapi import APIRouter, HTTPException

from quest_rag.core.config import get_retrieval_config, set_config_cache
from quest_rag.rag.pg_store import (
    get_evaluation_run,
    init_db,
    list_system_configs,
    set_system_config,
)
from quest_rag.schemas.schemas import CommonResponse

router = APIRouter(prefix="/system", tags=["SYSTEM"])


@router.post("/config/list")
def list_configs():
    init_db()
    return list_system_configs()


@router.put("/config")
def update_config(payload: dict):
    init_db()
    key = payload.get("key")
    value = payload.get("value")
    if not key or value is None:
        raise HTTPException(status_code=400, detail="缺少 key 或 value 字段")
    description = payload.get("description", "")
    result = set_system_config(key, value, description)
    set_config_cache(key, value)
    return result


@router.post("/config/retrieval/sync", response_model=CommonResponse)
def sync_retrieval_config(payload: dict):
    init_db()
    run_id = payload.get("run_id")
    if not run_id:
        raise HTTPException(status_code=400, detail="缺少 run_id 字段")
    run = get_evaluation_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="评测记录不存在")
    retrieval_opts = run.get("retrieval_options") or {}
    if not retrieval_opts:
        raise HTTPException(status_code=400, detail="该评测记录没有检索参数")
    params = {
        "top_k": retrieval_opts.get("top_k", 5),
        "recall_k": retrieval_opts.get("recall_k", 15),
        "mode": retrieval_opts.get("mode", "hybrid"),
        "rrf_k": retrieval_opts.get("rrf_k", 60),
    }
    set_system_config("retrieval", params, f"从评测记录 {run['name']} 同步")
    set_config_cache("retrieval", params)
    return CommonResponse(success=True, message=f"检索参数已同步自评测记录：{run['name']}")


@router.get("/config/retrieval")
def get_retrieval():
    init_db()
    return get_retrieval_config()
