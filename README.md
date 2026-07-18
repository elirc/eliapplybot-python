# eliapplybot-python

A local-first, review-first Python rebuild of the `eli apply mate` idea.

This app opens job application pages in a Playwright-controlled Chromium browser, scans visible form fields, maps high-confidence fields from a locally stored candidate profile, fills only safe high-confidence values, and prints a review report. It never submits applications.

## Safety model

- Local SQLite storage only.
- No cloud backend, remote database, or AI API dependency.
- Manual login is supported through the visible browser.
- CAPTCHAs, bot checks, rate limits, paywalls, and login restrictions are not bypassed.
- Final buttons such as submit, apply, send, finish, and complete are detected but never clicked.
- Resume upload fields are detected and the local path can be shown in the report, but files are not uploaded automatically in this first build.
- Long-form answers are suggested from the local answer bank and require review.

## Setup

```powershell
cd "C:\Users\Owner\Desktop\_Organized Desktop\08 App And Product Projects\eliapplybot-python"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m playwright install chromium
```

Any Python 3.11+ executable works.

## Initialize and import the sample profile

```powershell
eliapplybot init-db
eliapplybot import-profile tests\fixtures\sample_profile.json
eliapplybot export-profile output\profile.json
```

Edit the exported JSON or create your own profile JSON before using real personal data.

## Run against the fake local application page

Use a `file:///` URL for the included fixture:

```powershell
eliapplybot run "file:///C:/Users/Owner/Desktop/_Organized%20Desktop/08%20App%20And%20Product%20Projects/eliapplybot-python/tests/fixtures/fake_application.html" --report reports\fake-run.json
```

Workflow:

1. Chromium opens with a persistent local browser profile.
2. Log in or navigate manually if needed.
3. Press Enter in the terminal when the form is ready.
4. The app scans fields and fills high-confidence values.
5. Review the terminal report and JSON report.
6. Complete uncertain, skipped, or required fields manually.
7. Submit only when you personally decide to do so.

## CLI commands

```powershell
eliapplybot init-db
eliapplybot import-profile tests\fixtures\sample_profile.json
eliapplybot export-profile output\profile.json
eliapplybot add-job "https://example.com/job"
eliapplybot list-jobs
eliapplybot scan "https://example.com/job"
eliapplybot run "https://example.com/job"
eliapplybot show-attempt 1
```

`scan` opens the page and produces review entries without filling fields. `run` fills only high-confidence fields. Both accept `--headless` (mainly for testing against local fixture pages) and `--report <path>` for a JSON report.

## Optional local dashboard

The dashboard is intentionally small in this first build:

```powershell
uvicorn eliapplybot.web.app:app --reload
```

Open `http://127.0.0.1:8000`.

## Tests and linting

```powershell
pytest
ruff check .
ruff format .
```

The current tests are unit-level and storage-level. Browser integration tests are documented in `ROADMAP.md`.

## Project structure

- `src/eliapplybot/models.py` - Pydantic profile, detection, match, and result models.
- `src/eliapplybot/storage.py` - SQLite persistence for profiles, jobs, attempts, detections, fill logs, and review notes.
- `src/eliapplybot/scanner.py` - Playwright-backed page and iframe field scanner.
- `src/eliapplybot/matcher.py` - deterministic mapping rules.
- `src/eliapplybot/filler.py` - high-confidence Playwright filling and clearing support.
- `src/eliapplybot/review.py` - terminal and JSON review reports.
- `src/eliapplybot/adapters/` - ATS adapter interface and first-pass Greenhouse, Lever, Ashby, Workday, and generic adapters.

