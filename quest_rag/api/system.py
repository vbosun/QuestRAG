from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from quest_rag.auth.dependencies import require_permission
from quest_rag.auth.schemas import CurrentUser
from quest_rag.core.config import get_generation_config, get_retrieval_config, set_config_cache
from quest_rag.rag.pg_store import (
    get_evaluation_run,
    init_db,
    list_system_configs,
    set_system_config,
)
from quest_rag.schemas.schemas import CommonResponse, GenerationConfig, RetrievalOptions

router = APIRouter(prefix="/system", tags=["SYSTEM"])


@router.post("/config/list")
def list_configs(current_user: CurrentUser = Depends(require_permission("system.retrieval_config.view"))):
    init_db()
    return list_system_configs()


@router.put("/config")
def update_config(payload: dict, current_user: CurrentUser = Depends(require_permission("system.retrieval_config.update"))):
    init_db()
    key = payload.get("key")
    value = payload.get("value")
    if not key or value is None:
        raise HTTPException(status_code=400, detail="缺少 key 或 value 字段")
    try:
        if key == "retrieval":
            value = RetrievalOptions(**value).model_dump()
        elif key == "generation":
            value = GenerationConfig(**value).model_dump()
    except (TypeError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail="配置参数不符合范围要求") from exc
    description = payload.get("description", "")
    result = set_system_config(key, value, description)
    set_config_cache(key, value)
    return result


@router.post("/config/retrieval/sync", response_model=CommonResponse)
def sync_retrieval_config(payload: dict, current_user: CurrentUser = Depends(require_permission("system.retrieval_config.update"))):
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
    retrieval_params = {
        "top_k": retrieval_opts.get("top_k", 5),
        "recall_k": retrieval_opts.get("recall_k", 15),
        "mode": retrieval_opts.get("mode", "hybrid"),
        "rrf_k": retrieval_opts.get("rrf_k", 60),
    }
    retrieval_params = RetrievalOptions(**retrieval_params).model_dump()
    generation_opts = run.get("generation_options") or {}
    generation_params = GenerationConfig(
        temperature=generation_opts.get("temperature", 0.3),
        top_p=generation_opts.get("top_p", 0.9),
    ).model_dump()
    set_system_config("retrieval", retrieval_params, f"从评测记录 {run['name']} 同步")
    set_system_config("generation", generation_params, f"从评测记录 {run['name']} 同步")
    set_config_cache("retrieval", retrieval_params)
    set_config_cache("generation", generation_params)
    return CommonResponse(success=True, message=f"检索参数与生成参数已同步自评测记录：{run['name']}")


@router.get("/config/retrieval")
def get_retrieval(current_user: CurrentUser = Depends(require_permission("system.retrieval_config.view"))):
    init_db()
    return get_retrieval_config()


@router.get("/config/generation")
def get_generation(current_user: CurrentUser = Depends(require_permission("system.retrieval_config.view"))):
    init_db()
    return get_generation_config()
