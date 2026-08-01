from fastapi import APIRouter, Request, Depends, HTTPException

from quest_rag.auth.dependencies import get_current_user
from quest_rag.auth.schemas import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    ChangePasswordRequest,
    CurrentUser,
    UserInfo,
)
from quest_rag.auth.service import login, refresh_access_token, logout, change_password, AuthError
from quest_rag.auth.store import get_account_by_id
from quest_rag.auth.security import mask_id_number, normalize_id_number, get_sm2_public_key, sm2_decrypt

router = APIRouter(prefix="/auth", tags=["AUTH"])


@router.get("/public-key")
def public_key_endpoint():
    return {"public_key": get_sm2_public_key(), "algorithm": "SM2"}


@router.post("/login", response_model=LoginResponse)
def login_endpoint(req: LoginRequest, request: Request):
    try:
        id_number = sm2_decrypt(req.id_number)
        password = sm2_decrypt(req.password)
    except ValueError:
        raise HTTPException(status_code=400, detail={"code": "DECRYPT_FAILED", "message": "数据解密失败"})

    try:
        return login(
            id_number=id_number,
            password=password,
            login_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
        )
    except AuthError as e:
        raise HTTPException(status_code=e.http_status, detail={"code": e.code, "message": e.message})


@router.post("/refresh", response_model=RefreshResponse)
def refresh_endpoint(req: RefreshRequest):
    try:
        return refresh_access_token(req.refresh_token)
    except AuthError as e:
        raise HTTPException(status_code=e.http_status, detail={"code": e.code, "message": e.message})


@router.post("/logout")
def logout_endpoint(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        logout(
            sid=current_user.sid,
            user_id=current_user.id,
            request_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
        )
    except AuthError as e:
        raise HTTPException(status_code=e.http_status, detail={"code": e.code, "message": e.message})
    return {"success": True, "message": "退出登录成功"}


@router.get("/me", response_model=UserInfo)
def me_endpoint(current_user: CurrentUser = Depends(get_current_user)):
    account = get_account_by_id(current_user.id)
    if account is None:
        raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND", "message": "用户不存在"})

    normalized = normalize_id_number(account.get("id_number_ciphertext") or "")
    return UserInfo(
        id=account["id"],
        full_name=account["full_name"],
        id_number_masked=mask_id_number(normalized) if normalized else "",
        role=account["role"],
        roles=current_user.roles,
        permissions=current_user.permissions,
        rag_scopes=current_user.rag_scopes,
    )


@router.post("/change-password")
def change_password_endpoint(
    req: ChangePasswordRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        old_password = sm2_decrypt(req.old_password)
        new_password = sm2_decrypt(req.new_password)
        confirm_password = sm2_decrypt(req.confirm_password)
    except ValueError:
        raise HTTPException(status_code=400, detail={"code": "DECRYPT_FAILED", "message": "数据解密失败"})

    try:
        change_password(
            user_id=current_user.id,
            old_password=old_password,
            new_password=new_password,
            confirm_password=confirm_password,
            request_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
        )
    except AuthError as e:
        raise HTTPException(status_code=e.http_status, detail={"code": e.code, "message": e.message})
    return {"success": True, "message": "密码已修改，请重新登录"}
