import uvicorn
from fastapi import FastAPI
from quest_rag.logger import logger

from quest_rag.api import chat, document, evaluation, system, auth, permission
from quest_rag.core.config import load_system_config
from quest_rag.rag.pg_store import init_db
from quest_rag.auth.store import init_auth_db
from quest_rag.auth.permission_store import init_permission_db
from quest_rag.auth.permissions import seed_default_permissions

app = FastAPI()
app.include_router(chat.router)
app.include_router(document.router)
app.include_router(evaluation.router)
app.include_router(system.router)
app.include_router(auth.router)
app.include_router(permission.router)


@app.on_event("startup")
def startup():
    try:
        init_db()
        init_auth_db()
        init_permission_db()
        seed_default_permissions()
        load_system_config()
    except Exception as exc:
        logger.warning(f"PostgreSQL 初始化失败，评测工作台暂不可用: {exc}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8010)
