from fastapi import Header, HTTPException, Depends

from quest_rag.auth.schemas import CurrentUser
from quest_rag.auth.service import get_current_user_from_token, AuthError


def get_current_user(
    authorization: str = Header(None),
) -> CurrentUser:
    try:
        return get_current_user_from_token(authorization)
    except AuthError as e:
        raise HTTPException(status_code=e.http_status, detail={"code": e.code, "message": e.message})


def require_role(*roles: str):
    def dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "权限不足"})
        return current_user

    return dependency
