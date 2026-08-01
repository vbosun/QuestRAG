import json
import uuid
from datetime import datetime, timezone

import redis

from quest_rag.core.config import REDIS_URL, AUTH_REFRESH_TOKEN_HOURS, AUTH_LOGIN_FAIL_LIMIT, AUTH_LOGIN_LOCK_MINUTES

_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        if not REDIS_URL:
            raise RuntimeError("REDIS_URL is not configured")
        _redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


SESSION_PREFIX = "auth:session:"
USER_SESSIONS_PREFIX = "auth:user_sessions:"
LOGIN_FAIL_PREFIX = "auth:login_fail:"


def create_session(
    user_id: int,
    role: str,
    status: int,
    token_version: int,
    login_ip: str | None = None,
    user_agent: str | None = None,
) -> str:
    r = get_redis()
    sid = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    ttl = AUTH_REFRESH_TOKEN_HOURS * 3600
    expires_at = now.timestamp() + ttl
    session_data = {
        "sid": sid,
        "user_id": user_id,
        "role": role,
        "status": status,
        "token_version": token_version,
        "login_ip": login_ip or "",
        "user_agent": user_agent or "",
        "created_at": now.isoformat(),
        "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
    }
    key = f"{SESSION_PREFIX}{sid}"
    r.setex(key, ttl, json.dumps(session_data, ensure_ascii=False))
    r.sadd(f"{USER_SESSIONS_PREFIX}{user_id}", sid)
    r.expire(f"{USER_SESSIONS_PREFIX}{user_id}", ttl)
    return sid


def get_session(sid: str) -> dict | None:
    r = get_redis()
    data = r.get(f"{SESSION_PREFIX}{sid}")
    if data is None:
        return None
    return json.loads(data)


def delete_session(sid: str):
    r = get_redis()
    session = get_session(sid)
    r.delete(f"{SESSION_PREFIX}{sid}")
    if session:
        r.srem(f"{USER_SESSIONS_PREFIX}{session['user_id']}", sid)


def delete_all_user_sessions(user_id: int):
    r = get_redis()
    members = r.smembers(f"{USER_SESSIONS_PREFIX}{user_id}")
    for sid in members:
        r.delete(f"{SESSION_PREFIX}{sid}")
    r.delete(f"{USER_SESSIONS_PREFIX}{user_id}")


def get_login_fail_count(id_number_digest: str) -> int:
    r = get_redis()
    key = f"{LOGIN_FAIL_PREFIX}{id_number_digest}"
    val = r.get(key)
    return int(val) if val else 0


def increment_login_fail(id_number_digest: str) -> int:
    r = get_redis()
    key = f"{LOGIN_FAIL_PREFIX}{id_number_digest}"
    count = r.incr(key)
    r.expire(key, AUTH_LOGIN_LOCK_MINUTES * 60)
    return count


def delete_login_fail(id_number_digest: str):
    r = get_redis()
    r.delete(f"{LOGIN_FAIL_PREFIX}{id_number_digest}")


def is_login_locked(id_number_digest: str) -> bool:
    return get_login_fail_count(id_number_digest) >= AUTH_LOGIN_FAIL_LIMIT
