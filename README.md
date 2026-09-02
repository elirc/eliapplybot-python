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
cd <path-to>\eliapplybot-python
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m playwright install chromium
```

Any Python 3.11+ executable works.

## Create your profile

```powershell
eliapplybot new-profile output\my-profile.json
# edit output\my-profile.json with your real details, then:
eliapplybot import-profile output\my-profile.json
```

`new-profile` writes a placeholder template; every value in it must be replaced
with your own information before real use. `import-profile` validates the JSON
and warns if `documents.resume_path` or `cover_letter_path` do not exist on
this machine. `export-profile output\profile.json` writes the stored profile
back out for editing; re-import after editing.

## Try it against the fake local application page first

Use a `file:///` URL for the included fixture (adjust the path to where this
repo lives):

```powershell
eliapplybot run "file:///<path-to>/eliapplybot-python/tests/fixtures/fake_application.html" --report reports\fake-run.json
```

Add `--headless --no-input --close-browser` to run it fully unattended against
the fixture. Do not use `--no-input` on real job pages; the prompt is what
gives you time to log in and get the form on screen before scanning.

## Real use

```powershell
eliapplybot run "https://boards.greenhouse.io/<company>/jobs/<id>" --report reports\job.json
```

1. Chromium opens with a persistent local browser profile (logins are remembered
   between runs).
2. Log in or navigate manually until the application form is on screen.
3. Press Enter in the terminal; the app scans and fills only high-confidence
   fields, verifying each value after filling.
4. Custom dropdowns (Greenhouse/Lever-style comboboxes) are opened and an
   option is clicked only when it matches your saved answer exactly (or is the
   single "decline to answer"-style option when your saved EEO answer declines).
5. Review the terminal/JSON report, complete the uncertain and skipped fields,
   upload your resume yourself, and submit only when you decide to.

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
eliapplybot new-profile output\my-profile.json
eliapplybot import-profile output\my-profile.json
eliapplybot export-profile output\profile.json
eliapplybot add-job "https://example.com/job"
eliapplybot list-jobs
eliapplybot set-status 1 applied
eliapplybot scan "https://example.com/job"
eliapplybot run "https://example.com/job"
eliapplybot show-attempt 1
```

`scan` opens the page and produces review entries without filling fields. `run` fills only high-confidence fields. Both accept `--headless` and `--no-input` (mainly for testing against local fixture pages) and `--report <path>` for a JSON report. `set-status` tracks a job through saved, applied, interviewing, offer, rejected, or withdrawn.

## Optional local dashboard

```powershell
uvicorn eliapplybot.web.app:app --reload
```

Open `http://127.0.0.1:8000`. The dashboard lists your jobs (with an inline
status dropdown for tracking), recent fill attempts with filled/uncertain/failed
counts, and a per-attempt fill log showing what was filled and why. Values are
masked before storage, so the fill log never contains your full email or phone
number.

## Tests and linting

```powershell
pytest
ruff check .
ruff format .
```

Tests cover the matcher and storage at unit level plus headless-Chromium
integration tests (`tests/test_browser.py`) that scan and fill the local
fixtures, including custom combobox widgets, and assert that submit is never
clicked. The browser tests skip automatically if Chromium is not installed.

## Project structure

- `src/eliapplybot/models.py` - Pydantic profile, detection, match, and result models.
- `src/eliapplybot/storage.py` - SQLite persistence for profiles, jobs, attempts, detections, fill logs, and review notes.
- `src/eliapplybot/scanner.py` - Playwright-backed page and iframe field scanner.
- `src/eliapplybot/matcher.py` - deterministic mapping rules.
- `src/eliapplybot/filler.py` - high-confidence Playwright filling and clearing support.
- `src/eliapplybot/review.py` - terminal and JSON review reports.
- `src/eliapplybot/adapters/` - ATS adapter interface and first-pass Greenhouse, Lever, Ashby, Workday, and generic adapters.

