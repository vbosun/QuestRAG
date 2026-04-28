import uvicorn
from fastapi import FastAPI

from quest_rag.api import chat, document
from quest_rag.rag.embedding import add_documents
from quest_rag.rag.generator import generate
from quest_rag.rag.loader import load_file
from quest_rag.rag.retriever import search
from quest_rag.rag.splitter import split_docs

app = FastAPI()
app.include_router(chat.router)
app.include_router(document.router)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8010)
