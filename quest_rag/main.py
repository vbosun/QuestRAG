from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from quest_rag.api import chat, document

app = FastAPI()
app.include_router(chat.router)
app.include_router(document.router)

STATIC_DIR = Path(__file__).parent / "static"
WEB_DIST_DIR = Path(__file__).parent.parent / "web" / "dist"
WEB_ASSETS_DIR = WEB_DIST_DIR / "assets"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if WEB_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=WEB_ASSETS_DIR), name="web-assets")


@app.get("/", include_in_schema=False)
def index():
    if WEB_DIST_DIR.exists():
        return FileResponse(
            WEB_DIST_DIR / "index.html",
            headers={"Cache-Control": "no-cache"},
        )
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-cache"},
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8010)
