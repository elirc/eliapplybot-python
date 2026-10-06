# eliapplybot — Project Documentation

One-page reference for the project: what it is and how to use it (README), how
it is built (summary), and what has changed since the initial commit
(changelog), plus a traced walkthrough, code-review notes, and practice
exercises for developers learning the codebase.

> **Status note (2026-10-06):** This was checked against `main` @ `a4ad16c`
> (v1.0.0). `pytest` collects 48 tests. On a machine without Playwright's
> Chromium, 43 pass and the 5 browser tests in `tests/test_browser.py` are
> skipped. Sections 4-6 are new. Their file:line cites refer to that commit.

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
  the fill log (`storage.py:267`) and the report (`review.py:156`). The raw
  scan snapshot is **not** masked; see section 5, note 3.

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
                # (the 5 browser tests skip without `playwright install chromium`)
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

---

## 4. Walkthrough: one `eliapplybot run <url>`

Follow these cites in your editor. They are verified against `a4ad16c`.

1. **CLI.** `cli.py:18-108` builds the argparse tree, loads `AppConfig.from_env()`
   (`config.py:18`), and maps `--headless` and `--db` onto it (`cli.py:90-93`).
   Pydantic, JSON and lookup errors become one-line messages (`cli.py:99-108`).
   `run` dispatches to `run_application` (`cli.py:167-176`). `--no-input`
   becomes `interactive=False`.
2. **Attempt bookkeeping.** `workflow.py:27-31` loads the named profile, then
   creates or reuses the job row (`add_job` dedupes by URL, `storage.py:166-179`),
   picks an adapter, and opens an attempt row.
3. **Browser.** `BrowserController` launches a *persistent* Chromium context
   (`browser.py:21-23`), so logins and Chromium's own autofill survive between
   runs. `adapter.wait_ready` waits up to 8 s for `networkidle` and ignores
   failures (`adapters/base.py:23-25`).
4. **Human gate.** `workflow.py:37-40` blocks on `input(...)` until you press
   Enter. This is the only point where you log in or navigate.
5. **Scan.** `scan_page` (`scanner.py:235`) runs one in-page JS function in
   every frame (`scanner.py:237`). It returns visible inputs, selects,
   textareas, radio/checkbox groups, buttons, and ARIA combobox/listbox
   widgets. Each field records its `frame_index` and a CSS `selector` for the
   filler. `adapter.normalize_field` is applied (`workflow.py:42`), but every
   adapter inherits the identity version (`adapters/base.py:27-28`).
6. **Snapshot.** `storage.save_detections` (`storage.py:240-251`) stores every
   field as JSON, including `current_value`.
7. **Match.** `match_field` (`matcher.py:76-158`) runs ordered guards. Buttons
   are always `SKIP` (`:85-96`). Uploads become `SKIP`, or `MEDIUM` with the
   resume path shown (`:98-118`). Long-answer textareas are `MEDIUM`, with an
   answer-bank suggestion if one matches (`:120-139`). Then the first of
   `match_personal`, `match_authorization`, `match_eeo`,
   `match_experience_years`, `match_education`, `match_experience` and
   `match_preferences` that returns a result wins (`:141-152`). If none does,
   the field is `LOW`.
8. **Fill.** `fill_matches` (`filler.py:15-33`) passes only `HIGH` matches to
   `fill_one`. `fill_one` (`filler.py:36-93`) does the following:
   - selects choose an exact option;
   - radios and checkboxes click an exact option label;
   - comboboxes open, and click only an exact (or single decline-style)
     option, else press Escape (`filler.py:103-148`);
   - native `date` inputs need `YYYY-MM-DD`;
   - text is filled and then **read back**. A mismatch is reported as
     `FAILED` (`filler.py:76-84`).
9. **Persist and report.** `save_fill_results` masks `value_preview` with
   `mask_value` (`storage.py:253-284`, `review.py:12-28`). `build_report`
   (`review.py:31-78`) counts actions, lists empty required fields and
   possible final buttons, and adds the manual checklist. The text report is
   printed, and the JSON report is written if `--report` was given.
10. **Close.** With `--close-browser`, `clear_filled` restores the pre-fill
    values of text and select fills before the context closes
    (`workflow.py:78-79`, `filler.py:173-197`). Otherwise the browser stays
    open until you press Enter again.

---

## 5. Code-review notes (verified 2026-10-06)

Each note was reproduced against `a4ad16c` with a short script that imports
`src/` directly. No browser was needed.

1. **High-confidence fills overwrite existing answers.** Neither `match_field`
   nor `fill_one` looks at `field.current_value` before filling. A "First
   name" input that already contains `"Already typed"` still maps `HIGH` to
   the profile value, and `locator.fill` replaces it (`filler.py:76-77`).
   Because the browser profile is persistent (`browser.py:21`), Chromium's own
   autofill can pre-populate fields between runs. The sibling Chrome extension
   refuses to replace a non-empty value.
2. **Years-of-experience matching depends on insertion order.**
   `match_experience_years` returns the first skill whose `\b...\b` pattern
   appears (`matcher.py:311-317`). With
   `years_of_experience = {"react": 4, "react native": 1}`, the question
   "Years of React Native experience" maps `HIGH` to **4**.
3. **The raw scan snapshot is stored unmasked.** `save_detections` writes
   `field.model_dump_json()` (`storage.py:250`), so a pre-filled email ends up
   in `field_detections.field_json`. `show-attempt` prints it in full
   (`storage.py:314-346`, `cli.py:164-166`). The README's "fill log never
   contains your full email" is true only for `fill_logs`.
4. **Adapter host matching is a substring test.** `Adapter.matches` uses
   `pattern in hostname` (`adapters/base.py:19-21`), so both
   `greenhouse.io.example.org` and `notgreenhouse.io` resolve to the
   Greenhouse adapter. The impact is small today, because adapters only
   contribute a name and warnings, but it would matter once
   `normalize_field` does real work.
5. **Dead code.** `review.SENSITIVE_KEYS` (`review.py:9`) is never read, and
   `mask_value` re-implements the same key checks inline. The `review_notes`
   table (`storage.py:88`) is created but never written or read.
   `known_label_quirks` is set on every adapter but never used.

---

## 6. Exercises

Run all of these from the repo root with `pytest`. You do not need Chromium
for any of them.

### 6.1 Pin the masking rules (easy)

**Goal:** `mask_value` has no direct unit test. The web test checks it only
through the dashboard. Add `tests/test_review.py`.
**Hints:** Read `review.py:12-28`. Cover email, phone, address, an
over-120-character value, and a `documents.resume_path` key (which is *not*
masked).
**Check:** `pytest tests/test_review.py` passes, with assertions including
`mask_value("email", "eli@example.com") == "el***@example.com"` and
`mask_value("phone", "555-010-1234") == "***-***-1234"`.

### 6.2 Longest skill wins (easy-medium)

**Goal:** Fix note 2.
**Hints:** Sort `profile.years_of_experience.items()` by normalized skill
length, longest first, before the loop at `matcher.py:311`. Keep the
`re.escape` and the word boundaries.
**Check:** A new test in `tests/test_matcher.py` builds a profile with
`{"react": 4, "react native": 1}` and asserts that "Years of React Native
experience" returns `value == "1"`, while "Years of React experience" still
returns `"4"`. The full `pytest` run stays green.

### 6.3 Anchor adapter hostnames (medium)

**Goal:** Fix note 4 without breaking real hosts.
**Hints:** Match `hostname == pattern or hostname.endswith("." + pattern)`.
Check every `host_patterns` tuple in `adapters/`.
**Check:** A new `tests/test_adapters.py` asserts the following:
- `adapter_for_url("https://boards.greenhouse.io/x").name == "greenhouse"`
- `adapter_for_url("https://acme.wd5.myworkdayjobs.com/x").name == "workday"`
- `adapter_for_url("https://greenhouse.io.example.org/x").name == "generic"`
- `adapter_for_url("https://notgreenhouse.io/x").name == "generic"`

### 6.4 Never overwrite an existing text answer (medium)

**Goal:** Fix note 1 for text-like inputs.
**Hints:** Add the guard in `match_field` (after the button and upload
checks) for `element_type in {"input", "textarea"}` and non-choice input
types. Return `MEDIUM` with a clear reason. Do **not** apply it to selects,
because their `current_value` is the visible option text, which is often a
"Select..." placeholder.
**Check:** In `tests/test_matcher.py`, a `DetectedField` labelled "First name"
with `current_value="Already typed"` no longer returns `Confidence.HIGH`. The
same field with `current_value=""` still returns `HIGH` with value `"Eli"`
(from `tests/fixtures/sample_profile.json`). All 48 existing tests still pass
or skip as before.

### 6.5 Mask the scan snapshot (medium-hard)

**Goal:** Fix note 3 so that `field_detections` never holds a raw email or
phone number.
**Hints:** You could mask `current_value` in `save_detections`, but the
field does not know its profile key yet. A key-free approach works from the
field's `input_type` (`email`, `tel`) and its label text. Decide whether
`show-attempt` should still show anything useful.
**Check:** A test in `tests/test_storage.py` saves a `DetectedField` with
`input_type="email"` and `current_value="eli@example.com"`, then asserts that
`"eli@example.com" not in json.dumps(storage.show_attempt(attempt_id))`.
Before your fix this assertion fails.

### 6.6 Give `review_notes` a job (hard)

**Goal:** The table at `storage.py:88` has no reader or writer. Add
`Storage.add_note` and `Storage.list_notes`, plus a CLI subcommand
`note <attempt_id> "text"`. Include the notes in `show_attempt`.
**Hints:** Read the `CREATE TABLE` for the columns. Follow the
`set-status` pattern in `cli.py:45-49` and `cli.py:143-145`. Unknown attempt
ids must produce a friendly `LookupError`.
**Check:** A storage test round-trips a note through `show_attempt(...)`, and
`eliapplybot --db <tmp>.db note 999 "x"` exits with `Error: ...`, not a
traceback.
