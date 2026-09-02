# eliapplybot — Project Documentation

One-page reference for the project: what it is and how to use it (README), how
it is built (summary), and what has changed since the initial commit
(changelog).

---

## 1. README

### What it is

eliapplybot is a **local-first, review-first** assistant for job application
forms. It opens a job application page in a Playwright-controlled Chromium
browser, scans the visible form fields, maps them against a locally stored
candidate profile using deterministic rules, fills **only high-confidence
values**, and prints a review report. It never submits an application — final
buttons (submit, apply, send, finish) are detected, reported, and deliberately
left unclicked.

### Safety model

- All data stays local: SQLite storage, no cloud backend. The one optional
  network feature is voice dictation, which sends only your recorded audio to
  the Groq Whisper API, and only when you use it.
- Manual login through the visible browser; CAPTCHAs, bot checks, and login
  restrictions are never bypassed.
- Submit/apply/send buttons are never clicked.
- Resume/cover-letter files are never uploaded automatically; the report shows
  the local path for you to upload manually.
- EEO/demographic questions are only answered when your saved answer matches an
  option exactly (or your saved answer is a "decline"-style answer and the form
  has exactly one "decline"-style option).
- Long-form questions are only ever *suggested* from your local answer bank,
  never silently filled.
- Sensitive values (email, phone, address) are masked before being written to
  the fill log.

### Setup

```powershell
cd <path-to>\eliapplybot-python
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m playwright install chromium
```

Requires Python 3.11+.

### Create your profile

```powershell
eliapplybot new-profile output\my-profile.json
# edit output\my-profile.json with your real details, then:
eliapplybot import-profile output\my-profile.json
```

`new-profile` writes a placeholder template — replace every value with your own
information before real use. `import-profile` validates the JSON (with clear
per-field error messages) and warns if the resume/cover-letter paths do not
exist on this machine.

### Everyday use

```powershell
# dry run against the included fixture first
eliapplybot run "file:///<path-to>/eliapplybot-python/tests/fixtures/fake_application.html" --report reports\fake-run.json

# real job page
eliapplybot run "https://boards.greenhouse.io/<company>/jobs/<id>" --report reports\job.json
```

1. Chromium opens with a persistent local profile (logins are remembered).
2. Navigate/log in until the form is on screen, then press Enter in the
   terminal.
3. The app scans, fills high-confidence fields (verifying each value after
   filling), and prints the review report.
4. Complete the uncertain/skipped fields, upload your resume yourself, and
   submit only when you decide to.

Track your pipeline:

```powershell
eliapplybot list-jobs
eliapplybot set-status 1 applied     # saved|applied|interviewing|offer|rejected|withdrawn
eliapplybot show-attempt 1
```

### Local dashboard

```powershell
uvicorn eliapplybot.web.app:app --reload   # http://127.0.0.1:8000
```

Shows jobs with inline status dropdowns, recent attempts with
filled/uncertain/failed counts, and a per-attempt fill log (masked values).
The `/dictate` page records audio in the browser and saves the transcript to
your answer bank.

### Voice dictation (optional)

Set `GROQ_API_KEY` in `.env` (free key, no card: `https://console.groq.com`)
to enable speech-to-text via Groq's `whisper-large-v3-turbo`. Dictate answers
on the dashboard's `/dictate` page or with
`eliapplybot transcribe clip.m4a --save-answer "Title" --tags "why, role"`.
Saved answers are suggested automatically when a matching long-form question
appears on an application form. Only the audio you transcribe is sent to
Groq.

### Tests

```powershell
pytest          # 48 tests: unit + headless-Chromium integration + web routes
ruff check .
```

Browser tests skip automatically if Chromium is not installed.

---

## 2. Summary (architecture)

The pipeline is `scan → match → fill → report`, with storage and a small web
dashboard around it:

| Module | Role |
| --- | --- |
| `cli.py` | Argparse CLI: profile management, job tracking, `scan`/`run`, friendly error handling. |
| `workflow.py` | Orchestrates one attempt: open browser → wait for user → scan → match → fill → persist → report. |
| `browser.py` | Playwright Chromium with a persistent local user profile. |
| `scanner.py` | In-page JS that walks every frame and returns visible inputs, selects, textareas, radio/checkbox groups, buttons, and ARIA combobox/listbox widgets with their labels, options, and required flags. |
| `matcher.py` | Deterministic regex rules mapping detected fields to profile keys with `high`/`medium`/`low`/`skip` confidence. Handles personal info, work authorization, EEO (exact + decline-synonym options), education/experience incl. split month/year date controls, years-of-experience, preferences, and the answer bank. |
| `filler.py` | Fills only `high` matches: text fills verified by read-back, selects/radios by exact option match, custom dropdowns opened and clicked only on an exact (or single decline-style) option, native date inputs guarded. Everything else becomes review work. |
| `review.py` | Terminal + JSON report with masking, missing-required detection, final-button listing, and a manual checklist. |
| `storage.py` | SQLite: profiles, jobs (with tracking statuses), attempts, field detections, fill logs. |
| `adapters/` | Per-ATS metadata (Greenhouse, Lever, Ashby, Workday, generic): URL matching, quirks, warnings. |
| `web/` | FastAPI dashboard: jobs + status updates, attempts list, fill-log detail, browser dictation page. |
| `transcribe.py` | Optional Groq Whisper client for dictating answer-bank entries (opt-in via `GROQ_API_KEY`). |

Data model (`models.py`): pydantic `CandidateProfile` (contact, authorization,
EEO, education, experience, skills, documents, answer bank, preferences),
`DetectedField`, `FieldMatch`, `FillResult`, `JobRecord`,
`ApplicationAttempt`.

Test layout: `tests/test_matcher.py` (rule-level), `tests/test_storage.py`,
`tests/test_models.py`, `tests/test_web.py` (FastAPI TestClient),
`tests/test_browser.py` (headless Chromium against
`tests/fixtures/fake_application.html`, `custom_widgets.html`, and
`iframe_host.html`).

---

## 3. What changed (changelog)

### Initial commit `d8106db`

Local-first, review-first rebuild: scanner/matcher/filler pipeline, SQLite
storage, CLI, adapters, minimal read-only dashboard, 15 unit tests.

### `4df0178` — Harden scan/match/fill pipeline for real ATS pages

Focus: make the pipeline trustworthy on real Greenhouse/Lever/Ashby-style
pages.

- **Custom dropdowns (ARIA comboboxes)** — the filler now opens the widget,
  reads its options, and clicks one only if it exactly matches the saved
  answer (or is the single decline-style option for a decline-style EEO
  answer); otherwise it presses Escape and flags the field for review.
- **Decline-phrase synonyms** — "Decline to answer" safely matches "Decline To
  Self Identify" / "I don't wish to answer" when it is the only decline
  option.
- **Radio/checkbox groups without `<fieldset>`** get their real question as a
  label via `role="radiogroup"`, `aria-labelledby`, and nearby question text.
- **Post-fill verification** — every text fill is read back; a mismatch is
  reported as failed instead of silently trusted.
- **Fewer wrong fills** — ambiguous labels (Address line 2, Phone type,
  Country code, Preferred work location, …) demoted to review; added "right to
  work"/"authorised" phrasings; comboboxes no longer double-detected; buttons
  labeled by their visible text.
- **Usability** — `new-profile` template command, resume/cover-letter path
  existence warnings on import, auto `init-db` everywhere, `--no-input` flag
  for unattended fixture runs.
- **Tests 15 → 24** — new headless-Chromium integration tests
  (`test_browser.py`) and `custom_widgets.html` fixture proving combobox
  exact/decline selection, unsafe options left alone, and submit never
  clicked.

### `6134cab` — Date-part handling, job tracking, dashboard views, iframe coverage

Focus: the untested parts of the app plus top roadmap items.

- **Date fields** — separate month/year dropdowns get "September"/"2018"
  instead of an unfillable "09/2018"; `type=month` inputs get `2018-09`;
  native `type=date` inputs are review-only (no day is stored in the
  profile); end dates for a current role are review-only; GPA fields match.
- **Job tracking** — `set-status` CLI command and storage support for
  saved/applied/interviewing/offer/rejected/withdrawn, with validation.
- **Dashboard** — recent-attempts table with filled/uncertain/failed counts,
  per-attempt fill-log page with masked values, inline job-status dropdowns.
  New deps: `python-multipart` (form posts), `httpx` (dev, TestClient).
- **Iframe forms** — new `iframe_host.html` fixture and browser test proving
  cross-frame scan and fill (how many career pages embed their ATS).
- **CLI errors** — friendly one-line messages instead of tracebacks for a
  missing profile, unknown attempt/job id, missing file, or invalid profile
  JSON (which lists the exact bad fields).
- **Filler guard** — refuses to type a non-`YYYY-MM-DD` value into a native
  date input.
- **Tests 24 → 35** — web-route tests (including the masking guarantee),
  storage status/count tests, matcher date/GPA tests, iframe browser test,
  month/year selects added to the main fixture.

### `v1.0.0` — Voice dictation for the answer bank (Groq Whisper)

- New `transcribe.py` module calling Groq's `whisper-large-v3-turbo`
  (OpenAI-compatible endpoint) with clear errors for a missing key, oversized
  audio (25 MB free-tier limit), unsupported formats, and network failures.
- CLI `transcribe <audio>` prints the transcript;
  `--save-answer "Title" --tags ...` stores it in the profile's answer bank
  (same-id entries are replaced).
- Dashboard `/dictate` page: record in the browser (MediaRecorder), transcribe
  through the local server, edit, and save with tags; shows the current answer
  bank and a setup notice when no key is configured.
- Saved answers flow into the existing matcher suggestion path for long-form
  questions.
- `httpx` promoted to a runtime dependency; `GROQ_API_KEY` /
  `ELIAPPLYBOT_STT_MODEL` documented in `.env.example`.
- Tests 35 -> 48, all Groq calls mocked (no network or key needed in CI).
- Version bumped to 1.0.0.

### Known limitations (current)

- Workday multi-step, login-heavy flows still need manual navigation.
- Resume/cover-letter upload is manual by design.
- Long-form answers are suggested from the answer bank, never auto-filled.
- Next/continue/final buttons are never clicked.
