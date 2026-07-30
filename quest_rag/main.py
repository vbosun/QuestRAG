import uvicorn
from fastapi import FastAPI
from quest_rag.logger import logger

from quest_rag.api import chat, document, evaluation
from quest_rag.rag.pg_store import init_db

app = FastAPI()
app.include_router(chat.router)
app.include_router(document.router)
app.include_router(evaluation.router)


@app.on_event("startup")
def startup():
    try:
        init_db()
    except Exception as exc:
        logger.warning(f"PostgreSQL 初始化失败，评测工作台暂不可用: {exc}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8010)
