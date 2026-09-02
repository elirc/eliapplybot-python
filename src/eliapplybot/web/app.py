from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from eliapplybot.config import AppConfig
from eliapplybot.storage import JOB_STATUSES, Storage

WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=WEB_DIR / "templates")
app = FastAPI(title="eliapplybot local dashboard")
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")


def get_storage() -> Storage:
    config = AppConfig.from_env()
    storage = Storage(config.db_path)
    storage.init_db()
    return storage


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    config = AppConfig.from_env()
    storage = Storage(config.db_path)
    storage.init_db()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "jobs": storage.list_jobs(),
            "attempts": storage.list_attempts(),
            "db_path": config.db_path,
            "statuses": sorted(JOB_STATUSES),
        },
    )


@app.get("/attempts/{attempt_id}", response_class=HTMLResponse)
def attempt_detail(request: Request, attempt_id: int) -> HTMLResponse:
    storage = get_storage()
    try:
        data = storage.show_attempt(attempt_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request,
        "attempt.html",
        {
            "attempt": data["attempt"],
            "fields": data["fields"],
            "logs": data["logs"],
        },
    )


@app.post("/jobs/{job_id}/status")
def set_job_status(job_id: int, status: str = Form(...)) -> RedirectResponse:
    storage = get_storage()
    try:
        storage.update_job_status(job_id, status)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url="/", status_code=303)
