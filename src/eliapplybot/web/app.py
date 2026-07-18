from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from eliapplybot.config import AppConfig
from eliapplybot.storage import Storage

WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=WEB_DIR / "templates")
app = FastAPI(title="eliapplybot local dashboard")
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    config = AppConfig.from_env()
    storage = Storage(config.db_path)
    storage.init_db()
    jobs = storage.list_jobs()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"jobs": jobs, "db_path": config.db_path},
    )
