import uvicorn
from fastapi import FastAPI, HTTPException
from quest_rag.logger import logger

from quest_rag.api import applications, auth, browser, chat, document, evaluation, permission, public_services, system
from quest_rag.core.config import load_system_config
from quest_rag.rag.pg_store import init_db
from quest_rag.auth.store import init_auth_db
from quest_rag.auth.permission_store import init_permission_db
from quest_rag.auth.permissions import seed_default_permissions
from quest_rag.chat_memory.store import init_chat_memory_db
from quest_rag.social_security.store import init_social_security_db, seed_social_security_data
from quest_rag.subsidy.store import init_subsidy_db, seed_subsidy_rules
from quest_rag.applications.store import init_application_db

app = FastAPI()


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    import psycopg
    import redis
    from quest_rag.core.config import DATABASE_URL, REDIS_URL
    checks = {"postgresql": False, "redis": False}
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=3) as conn:
            row = conn.execute("SELECT to_regclass('auth_account') IS NOT NULL").fetchone()
            checks["postgresql"] = bool(row and row[0])
    except Exception:
        pass
    try:
        client = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=3, socket_timeout=3)
        try:
            checks["redis"] = bool(client.ping())
        finally:
            client.close()
    except Exception:
        pass
    if not all(checks.values()):
        raise HTTPException(status_code=503, detail={"status": "unavailable", "checks": checks})
    return {"status": "ready", "checks": checks}

app.include_router(chat.router)
app.include_router(document.router)
app.include_router(evaluation.router)
app.include_router(system.router)
app.include_router(auth.router)
app.include_router(permission.router)
app.include_router(public_services.router)
app.include_router(applications.router)
app.include_router(browser.router)


@app.on_event("startup")
def startup():
    try:
        init_db()
        init_auth_db()
        init_permission_db()
        seed_default_permissions()
        init_chat_memory_db()
        init_social_security_db()
        seed_social_security_data()
        init_subsidy_db()
        seed_subsidy_rules()
        init_application_db()
        load_system_config()
    except Exception as exc:
        logger.warning(f"PostgreSQL 初始化失败，评测工作台暂不可用: {exc}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8010)
