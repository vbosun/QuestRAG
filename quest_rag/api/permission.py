"""
权限管理 API：角色 CRUD、用户管理、权限目录。
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from quest_rag.auth.dependencies import require_permission
from quest_rag.auth.schemas import CurrentUser
from quest_rag.auth.security import hash_password, validate_password_policy
from quest_rag.auth import permission_store as ps
from quest_rag.auth.store import (
    get_account_by_id,
    insert_operation_log,
    create_personal_info,
    create_auth_account,
)
from quest_rag.auth.security import compute_id_number_digest, normalize_id_number
from pydantic import BaseModel, Field

router = APIRouter(prefix="/permissions", tags=["PERMISSION"])


# ── 请求体 schemas ─────────────────────────────────────────────────────

class RoleCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""


class RoleUpdate(BaseModel):
    role_id: int
    name: str | None = None
    description: str | None = None
    status: int | None = None


class RoleIdRequest(BaseModel):
    role_id: int


class PermissionCodes(BaseModel):
    role_id: int
    codes: list[str]


class UserCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=50)
    id_number: str = Field(..., min_length=17, max_length=18)
    password: str = Field(..., min_length=6)
    role_codes: list[str] = []


class UserUpdate(BaseModel):
    user_id: int
    full_name: str | None = None


class UserRoleUpdate(BaseModel):
    user_id: int
    role_codes: list[str]


class ResetPasswordBody(BaseModel):
    user_id: int
    new_password: str = Field(..., min_length=6)


class UserIdRequest(BaseModel):
    user_id: int


class UserListRequest(BaseModel):
    search: str = ""
    role_code: str = ""
    status: int | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# ── 工具函数 ───────────────────────────────────────────────────────────

def _log(user_id: int, action: str, request: Request, target_type: str = "", target_id: str = "", detail: dict | None = None):
    from quest_rag.auth.store import insert_operation_log
    insert_operation_log(
        user_id=user_id,
        action=action,
        request_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        target_type=target_type,
        target_id=target_id,
        detail=detail or {},
    )


# ── 权限目录 ───────────────────────────────────────────────────────────

@router.post("/catalog")
def get_catalog(current_user: CurrentUser = Depends(require_permission("permission.role.view"))):
    return ps.get_permission_catalog()


# ── 角色管理 ───────────────────────────────────────────────────────────

@router.post("/roles/list")
def list_roles(current_user: CurrentUser = Depends(require_permission("permission.role.view"))):
    return ps.list_roles()


@router.post("/roles/create")
def create_role_endpoint(req: RoleCreate, request: Request,
                         current_user: CurrentUser = Depends(require_permission("permission.role.create"))):
    role = ps.create_role(code=req.code, name=req.name, description=req.description)
    _log(current_user.id, "ROLE_CREATE", request, target_type="role", target_id=str(role["id"]),
         detail={"code": req.code, "name": req.name})
    return role


@router.post("/roles/get")
def get_role_endpoint(req: RoleIdRequest, current_user: CurrentUser = Depends(require_permission("permission.role.view"))):
    role = ps.get_role(req.role_id)
    if role is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "角色不存在"})
    return role


@router.post("/roles/update")
def update_role_endpoint(req: RoleUpdate, request: Request,
                         current_user: CurrentUser = Depends(require_permission("permission.role.update"))):
    role = ps.get_role(req.role_id)
    if role is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "角色不存在"})

    updated = ps.update_role(req.role_id, name=req.name, description=req.description, status=req.status)
    if req.status is not None and req.status != 1:
        ps.delete_sessions_by_role(req.role_id)
    _log(current_user.id, "ROLE_UPDATE", request, target_type="role", target_id=str(req.role_id),
         detail={"changes": req.model_dump(exclude_none=True, exclude={"role_id"})})
    return updated


@router.post("/roles/delete")
def delete_role_endpoint(req: RoleIdRequest, request: Request,
                         current_user: CurrentUser = Depends(require_permission("permission.role.delete"))):
    role = ps.get_role(req.role_id)
    if role is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "角色不存在"})
    if role["system_builtin"]:
        raise HTTPException(status_code=400, detail={"code": "BUILTIN", "message": "内置角色不可删除"})

    user_ids = ps.get_role_user_ids(req.role_id)
    if user_ids:
        admins = [
            uid for uid in user_ids
            if "ADMIN" in ps.get_user_roles(uid) and len(ps.get_user_roles(uid)) == 1
        ]
        if admins:
            raise HTTPException(status_code=400, detail={"code": "LAST_ADMIN", "message": "不能移除系统中最后一个管理员"})

    ps.delete_role(req.role_id)
    ps.delete_sessions_by_role(req.role_id)
    _log(current_user.id, "ROLE_DELETE", request, target_type="role", target_id=str(req.role_id),
         detail={"code": role["code"], "name": role["name"]})
    return {"success": True}


@router.post("/roles/permissions")
def set_role_permissions_endpoint(req: PermissionCodes, request: Request,
                                  current_user: CurrentUser = Depends(require_permission("permission.role.assign"))):
    role = ps.get_role(req.role_id)
    if role is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "角色不存在"})
    ps.set_role_permissions(req.role_id, req.codes)
    ps.delete_sessions_by_role(req.role_id)
    _log(current_user.id, "ROLE_ASSIGN_PERMISSION", request, target_type="role", target_id=str(req.role_id),
         detail={"codes": req.codes})
    return {"success": True}


@router.post("/roles/rag-scopes")
def set_role_rag_scopes_endpoint(req: PermissionCodes, request: Request,
                                 current_user: CurrentUser = Depends(require_permission("permission.role.assign"))):
    role = ps.get_role(req.role_id)
    if role is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "角色不存在"})
    ps.set_role_rag_scopes(req.role_id, req.codes)
    ps.delete_sessions_by_role(req.role_id)
    _log(current_user.id, "ROLE_ASSIGN_RAG_SCOPE", request, target_type="role", target_id=str(req.role_id),
         detail={"codes": req.codes})
    return {"success": True}


# ── 用户管理 ───────────────────────────────────────────────────────────

@router.post("/users/list")
def list_users_endpoint(
    req: UserListRequest,
    current_user: CurrentUser = Depends(require_permission("permission.user.view")),
):
    return ps.list_users(search=req.search, role_code=req.role_code, status=req.status, page=req.page, page_size=req.page_size)


@router.post("/users/create")
def create_user_endpoint(req: UserCreate, request: Request,
                         current_user: CurrentUser = Depends(require_permission("permission.user.create"))):
    try:
        normalized = normalize_id_number(req.id_number)
    except ValueError:
        raise HTTPException(status_code=400, detail={"code": "BAD_ID_NUMBER", "message": "身份证号格式不正确"})

    policy_error = validate_password_policy(req.password)
    if policy_error:
        raise HTTPException(status_code=400, detail={"code": "WEAK_PASSWORD", "message": policy_error})

    digest = compute_id_number_digest(normalized)
    personal_info_id = create_personal_info(digest, req.full_name, normalized)
    password_hash = hash_password(req.password)
    role_codes = req.role_codes or ["USER"]
    account_id = create_auth_account(personal_info_id, digest, password_hash, role="USER")

    ps.set_user_roles(account_id, role_codes)

    _log(current_user.id, "USER_CREATE", request, target_type="user", target_id=str(account_id),
         detail={"full_name": req.full_name, "role_codes": role_codes})
    return {"id": account_id, "full_name": req.full_name}


@router.post("/users/get")
def get_user_endpoint(req: UserIdRequest, current_user: CurrentUser = Depends(require_permission("permission.user.view"))):
    user = ps.get_user_detail(req.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "用户不存在"})
    return user


@router.post("/users/update")
def update_user_endpoint(req: UserUpdate, request: Request,
                         current_user: CurrentUser = Depends(require_permission("permission.user.update"))):
    user = ps.get_user_detail(req.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "用户不存在"})
    # 第一阶段 personal_info 表只有 full_name 可更新
    if req.full_name is not None:
        from quest_rag.auth.store import get_conn as auth_get_conn, get_account_by_id
        with auth_get_conn() as conn:
            account = get_account_by_id(req.user_id)
            if account:
                conn.execute(
                    "UPDATE personal_info SET full_name = %s, updated_at = now() WHERE id = %s",
                    (req.full_name, account["personal_info_id"]),
                )
    _log(current_user.id, "USER_UPDATE", request, target_type="user", target_id=str(req.user_id),
         detail=req.model_dump(exclude_none=True, exclude={"user_id"}))
    return ps.get_user_detail(req.user_id)


@router.post("/users/roles")
def update_user_roles_endpoint(req: UserRoleUpdate, request: Request,
                               current_user: CurrentUser = Depends(require_permission("permission.user.assign_role"))):
    if req.user_id == current_user.id:
        current_roles = ps.get_user_roles(req.user_id)
        if "ADMIN" in current_roles and "ADMIN" not in req.role_codes:
            raise HTTPException(status_code=400, detail={"code": "SELF_DEMOTE", "message": "不能移除自己的管理员角色"})

    ps.set_user_roles(req.user_id, req.role_codes)
    ps.delete_all_user_sessions(req.user_id)
    _log(current_user.id, "USER_ASSIGN_ROLE", request, target_type="user", target_id=str(req.user_id),
         detail={"role_codes": req.role_codes})
    return {"success": True}


@router.post("/users/reset-password")
def reset_password_endpoint(req: ResetPasswordBody, request: Request,
                            current_user: CurrentUser = Depends(require_permission("permission.user.reset_password"))):
    user = ps.get_user_detail(req.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "用户不存在"})

    policy_error = validate_password_policy(req.new_password)
    if policy_error:
        raise HTTPException(status_code=400, detail={"code": "WEAK_PASSWORD", "message": policy_error})

    new_hash = hash_password(req.new_password)
    ps.reset_user_password(req.user_id, new_hash)
    ps.delete_all_user_sessions(req.user_id)
    _log(current_user.id, "USER_RESET_PASSWORD", request, target_type="user", target_id=str(req.user_id))
    return {"success": True, "message": "密码已重置，用户需重新登录"}


@router.post("/users/lock")
def lock_user_endpoint(req: UserIdRequest, request: Request,
                       current_user: CurrentUser = Depends(require_permission("permission.user.lock"))):
    if req.user_id == current_user.id:
        raise HTTPException(status_code=400, detail={"code": "SELF_LOCK", "message": "不能锁定自己"})

    ps.lock_user(req.user_id)
    ps.delete_all_user_sessions(req.user_id)
    _log(current_user.id, "USER_LOCK", request, target_type="user", target_id=str(req.user_id))
    return {"success": True}


@router.post("/users/unlock")
def unlock_user_endpoint(req: UserIdRequest, request: Request,
                         current_user: CurrentUser = Depends(require_permission("permission.user.unlock"))):
    ps.unlock_user(req.user_id)
    _log(current_user.id, "USER_UNLOCK", request, target_type="user", target_id=str(req.user_id))
    return {"success": True}


@router.post("/users/enable")
def enable_user_endpoint(req: UserIdRequest, request: Request,
                         current_user: CurrentUser = Depends(require_permission("permission.user.unlock"))):
    ps.update_user_status(req.user_id, 1)
    _log(current_user.id, "USER_ENABLE", request, target_type="user", target_id=str(req.user_id))
    return {"success": True}


@router.post("/users/disable")
def disable_user_endpoint(req: UserIdRequest, request: Request,
                          current_user: CurrentUser = Depends(require_permission("permission.user.lock"))):
    if req.user_id == current_user.id:
        raise HTTPException(status_code=400, detail={"code": "SELF_DISABLE", "message": "不能禁用自己"})

    ps.update_user_status(req.user_id, 0)
    ps.delete_all_user_sessions(req.user_id)
    _log(current_user.id, "USER_DISABLE", request, target_type="user", target_id=str(req.user_id))
    return {"success": True}


@router.post("/users/kick")
def kick_user_endpoint(req: UserIdRequest, request: Request,
                       current_user: CurrentUser = Depends(require_permission("permission.user.kick"))):
    ps.delete_all_user_sessions(req.user_id)
    _log(current_user.id, "USER_KICK", request, target_type="user", target_id=str(req.user_id))
    return {"success": True, "message": "用户已被强制下线"}
