# Roadmap

This first build demonstrates the full local architecture, but it is intentionally conservative.

## Next practical improvements

- Add Playwright browser integration tests for the fake application fixture.
- Improve same-origin iframe selector stability and cross-frame reporting.
- Add richer adapter-specific scanner hints for Greenhouse, Lever, Ashby, and Workday.
- Add robust custom widget support for ARIA comboboxes/listboxes and Workday-style controls.
- Add an explicit review UI where each medium-confidence suggestion can be approved before filling.
- Add resume upload approval flow with file existence checks and clear confirmation.
- Add answer-bank search/edit UI and manual “fill this answer” controls.
- Add application tracking statuses: saved, applied, rejected, interviewing, offer, withdrawn.
- Add per-job notes and reusable final checklist templates.
- Add multi-profile support in the dashboard.
- Add a job queue with respectful pacing and no background mass-submit behavior.
- Add richer date handling for separate month/year controls and browser-native date/month inputs.
- Add better grouping for checkbox groups where multiple selections are appropriate.
- Add import helpers from the original extension profile shape if needed.

## Known limitations

- Workday support is partial; login-heavy and dynamic multi-step flows need manual navigation.
- The first build does not automatically upload resume or cover letter files.
- The first build does not click next/continue/final submit buttons.
- Long-form answers are only suggested; they are not silently filled.
- The local web dashboard is read-oriented; the CLI is the main workflow.
- Browser tests are not enabled by default because Playwright installation can be heavy.

