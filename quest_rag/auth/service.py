from quest_rag.auth import redis_store, security, store
from quest_rag.auth.schemas import LoginResponse, RefreshResponse, UserInfo


class AuthError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400):
        self.code = code
        self.message = message
        self.http_status = http_status


def login(id_number: str, password: str, login_ip: str | None = None, user_agent: str | None = None) -> LoginResponse:
    try:
        normalized = security.normalize_id_number(id_number)
    except ValueError:
        raise AuthError("INVALID_CREDENTIALS", "身份证号或密码错误", 401)

    digest = security.compute_id_number_digest(normalized)

    if redis_store.is_login_locked(digest):
        raise AuthError("ACCOUNT_LOCKED", "账号已被暂时锁定，请稍后再试", 403)

    account = store.get_account_by_id_number_digest(digest)

    if account is None:
        redis_store.increment_login_fail(digest)
        store.increment_failed_login(digest)
        store.insert_login_log(None, digest, login_ip, user_agent, 0, "ACCOUNT_NOT_FOUND")
        raise AuthError("INVALID_CREDENTIALS", "身份证号或密码错误", 401)

    if account["status"] == 0:
        raise AuthError("ACCOUNT_DISABLED", "账号已禁用，请联系管理员", 403)
    if account["status"] == -1:
        raise AuthError("ACCOUNT_LOCKED", "账号已被锁定，请联系管理员", 403)

    if not security.verify_password(password, account["password_hash"]):
        redis_store.increment_login_fail(digest)
        store.increment_failed_login(digest)
        store.insert_login_log(account["id"], digest, login_ip, user_agent, 0, "WRONG_PASSWORD")
        raise AuthError("INVALID_CREDENTIALS", "身份证号或密码错误", 401)

    redis_store.delete_login_fail(digest)

    sid = redis_store.create_session(
        user_id=account["id"],
        role=account["role"],
        status=account["status"],
        token_version=account["token_version"],
        login_ip=login_ip,
        user_agent=user_agent,
    )

    access_token = security.create_access_token(
        user_id=account["id"],
        sid=sid,
        role=account["role"],
        token_version=account["token_version"],
    )
    refresh_token = security.create_refresh_token(
        user_id=account["id"],
        sid=sid,
        token_version=account["token_version"],
    )

    store.update_last_login(account["id"], login_ip)
    store.insert_login_log(account["id"], digest, login_ip, user_agent, 1)
    store.insert_operation_log(account["id"], "LOGIN", login_ip, user_agent)

    from quest_rag.core.config import AUTH_ACCESS_TOKEN_MINUTES

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=AUTH_ACCESS_TOKEN_MINUTES * 60,
        user=UserInfo(
            id=account["id"],
            full_name=account["full_name"],
            id_number_masked=security.mask_id_number(normalized),
            role=account["role"],
        ),
    )


def refresh_access_token(refresh_token: str) -> RefreshResponse:
    try:
        payload = security.decode_token(refresh_token)
    except Exception:
        raise AuthError("INVALID_TOKEN", "token无效", 401)

    if payload.get("type") != "refresh":
        raise AuthError("INVALID_TOKEN", "token类型错误", 401)

    sid = payload.get("sid")
    if not sid:
        raise AuthError("INVALID_TOKEN", "token缺少session信息", 401)

    session = redis_store.get_session(sid)
    if session is None:
        raise AuthError("SESSION_EXPIRED", "登录已失效，请重新登录", 401)

    if str(session["user_id"]) != str(payload.get("sub")):
        raise AuthError("INVALID_TOKEN", "token与session不匹配", 401)

    if session["token_version"] != payload.get("token_version"):
        raise AuthError("SESSION_EXPIRED", "密码已修改，请重新登录", 401)

    new_access_token = security.create_access_token(
        user_id=session["user_id"],
        sid=sid,
        role=session["role"],
        token_version=session["token_version"],
    )

    from quest_rag.core.config import AUTH_ACCESS_TOKEN_MINUTES

    return RefreshResponse(
        access_token=new_access_token,
        token_type="Bearer",
        expires_in=AUTH_ACCESS_TOKEN_MINUTES * 60,
    )


def logout(sid: str, user_id: int, request_ip: str | None = None, user_agent: str | None = None):
    redis_store.delete_session(sid)
    store.insert_operation_log(user_id, "LOGOUT", request_ip, user_agent)


def change_password(
    user_id: int,
    old_password: str,
    new_password: str,
    confirm_password: str,
    request_ip: str | None = None,
    user_agent: str | None = None,
):
    if new_password != confirm_password:
        raise AuthError("PASSWORD_MISMATCH", "两次输入的新密码不一致")

    if old_password == new_password:
        raise AuthError("SAME_PASSWORD", "新密码不能与旧密码相同")

    policy_error = security.validate_password_policy(new_password)
    if policy_error:
        raise AuthError("WEAK_PASSWORD", policy_error)

    account = store.get_account_by_id(user_id)
    if account is None:
        raise AuthError("USER_NOT_FOUND", "用户不存在", 404)

    if not security.verify_password(old_password, account["password_hash"]):
        raise AuthError("WRONG_PASSWORD", "旧密码错误")

    new_hash = security.hash_password(new_password)
    store.update_password(user_id, new_hash)
    redis_store.delete_all_user_sessions(user_id)
    store.insert_operation_log(user_id, "CHANGE_PASSWORD", request_ip, user_agent)


def get_current_user_from_token(authorization: str | None) -> "CurrentUser":
    from quest_rag.auth.schemas import CurrentUser

    if not authorization:
        raise AuthError("UNAUTHORIZED", "未提供认证信息", 401)

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("UNAUTHORIZED", "认证格式错误", 401)

    try:
        payload = security.decode_token(token)
    except Exception:
        raise AuthError("INVALID_TOKEN", "token无效或已过期", 401)

    if payload.get("type") != "access":
        raise AuthError("INVALID_TOKEN", "token类型错误", 401)

    sid = payload.get("sid")
    if not sid:
        raise AuthError("INVALID_TOKEN", "token缺少session信息", 401)

    session = redis_store.get_session(sid)
    if session is None:
        raise AuthError("SESSION_EXPIRED", "登录已失效，请重新登录", 401)

    if str(session["user_id"]) != str(payload.get("sub")):
        raise AuthError("INVALID_TOKEN", "token与session不匹配", 401)

    if session["token_version"] != payload.get("token_version"):
        raise AuthError("SESSION_EXPIRED", "密码已修改，请重新登录", 401)

    account = store.get_account_by_id(session["user_id"])
    if account is None or account["status"] != 1:
        raise AuthError("ACCOUNT_DISABLED", "账号不可用", 403)

    normalized = security.normalize_id_number(account.get("id_number_ciphertext") or "")
    id_number_masked = security.mask_id_number(normalized) if normalized else None

    return CurrentUser(
        id=session["user_id"],
        sid=sid,
        role=session["role"],
        status=session["status"],
        full_name=account["full_name"],
        id_number_masked=id_number_masked,
        token_version=session["token_version"],
    )
