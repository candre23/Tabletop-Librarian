from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import APP_NAME, APP_VERSION, STATIC_DIR

logger = logging.getLogger(__name__)

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    docs_url=None,
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
async def startup_event() -> None:
    logger.info("%s v%s initialized", APP_NAME, APP_VERSION)


@app.get("/", response_class=HTMLResponse)
async def home() -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
    <title>{APP_NAME}</title>
    <link rel=\"stylesheet\" href=\"/static/css/main.css\">
</head>
<body>
    <main class=\"shell\">
        <section class=\"panel\">
            <div class=\"eyebrow\">v{APP_VERSION}</div>
            <h1>{APP_NAME}</h1>
            <p>The server is running.</p>
            <div class=\"status\"><span></span> Ready</div>
        </section>
    </main>
</body>
</html>"""
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "application": APP_NAME,
        "version": APP_VERSION,
    }
