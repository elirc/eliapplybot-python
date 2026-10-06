# Roadmap

This first build demonstrates the full local architecture, but it is intentionally conservative.

> **Status note (2026-10-06, v1.0.0 @ `a4ad16c`):** Every item under "Done since
> the first build" was checked against the code and is present. Every item
> under "Next practical improvements" is still open. In particular:
> - Adapters still only match hostnames. `normalize_field` is the identity in
>   every adapter (`src/eliapplybot/adapters/base.py:27-28`).
> - The dashboard saves dictated answers only to the `default` profile
>   (`web/app.py:94-116`).
> - A `review_notes` table exists (`storage.py:88`), but no code reads or
>   writes it.
>
> DOCS.md section 5 lists defects found during this check (overwriting
> pre-filled fields, skill-order matching, the unmasked scan snapshot, and
> substring host matching). DOCS.md section 6 turns each one into an exercise.

## Done since the first build

- Playwright browser integration tests for the fake application and custom
  widget fixtures (`tests/test_browser.py`).
- First-pass ARIA combobox/listbox support: the filler opens the widget and
  clicks only an exact (or single decline-style) option, else leaves it for
  review.
- Radio/checkbox group labels from `role="radiogroup"`/`aria-labelledby` and
  nearby question text when there is no `<fieldset>`.
- Post-fill verification: text inputs are read back after filling and reported
  as failed if the page shows a different value.
- `new-profile` template command, `--no-input` automation flag, and
  resume/cover-letter path existence warnings on import.
- Separate month/year date controls: month selects get month names, year
  selects get years, `type=month` inputs get `YYYY-MM`, and native `type=date`
  inputs are left for review (a full date is not stored). GPA fields match.
- Application tracking statuses via `set-status` (saved, applied, interviewing,
  offer, rejected, withdrawn), also editable from the dashboard.
- Dashboard attempts view with per-attempt fill logs and status dropdowns,
  covered by FastAPI TestClient tests.
- Same-origin iframe scan/fill covered by a browser integration test.
- Voice dictation for the answer bank via Groq Whisper (CLI `transcribe` and a
  dashboard record-and-save page); opt-in via `GROQ_API_KEY`.
- Friendly CLI error messages instead of tracebacks for missing profiles,
  attempts, files, and invalid JSON.

## Next practical improvements

- Add richer adapter-specific scanner hints for Greenhouse, Lever, Ashby, and Workday.
- Extend custom widget support to Workday-style multi-step controls.
- Add an explicit review UI where each medium-confidence suggestion can be approved before filling.
- Add resume upload approval flow with file existence checks and clear confirmation.
- Add per-job notes and reusable final checklist templates.
- Add multi-profile support in the dashboard.
- Add a job queue with respectful pacing and no background mass-submit behavior.
- Add better grouping for checkbox groups where multiple selections are appropriate.
- Add import helpers from the original extension profile shape if needed.

## Known limitations

- Workday support is partial; login-heavy and dynamic multi-step flows need manual navigation.
- The first build does not automatically upload resume or cover letter files.
- The first build does not click next/continue/final submit buttons.
- Long-form answers are only suggested; they are not silently filled.
- The CLI is the main workflow. The dashboard can change a job's status and
  save dictated answers, but it cannot import profiles or start runs.
- Browser tests skip automatically when Chromium is not installed.

