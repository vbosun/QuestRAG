import uvicorn
from fastapi import FastAPI

from quest_rag.api import chat, document

app = FastAPI()
app.include_router(chat.router)
app.include_router(document.router)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8010)
