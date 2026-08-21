from __future__ import annotations

from pathlib import Path

from eliapplybot.adapters import adapter_for_url
from eliapplybot.browser import BrowserController
from eliapplybot.config import AppConfig
from eliapplybot.filler import clear_filled, fill_matches
from eliapplybot.matcher import match_fields
from eliapplybot.models import FillAction, FillResult
from eliapplybot.review import build_report, render_text_report, write_json_report
from eliapplybot.scanner import scan_page
from eliapplybot.storage import Storage


def run_application(
    url: str,
    *,
    config: AppConfig,
    storage: Storage,
    profile_name: str = "default",
    review_only: bool = False,
    keep_browser_open: bool = True,
    report_path: str | Path | None = None,
    interactive: bool = True,
) -> dict[str, object]:
    storage.init_db()
    profile = storage.load_profile(profile_name)
    job_id = storage.add_job(url)
    adapter = adapter_for_url(url)
    attempt_id = storage.create_attempt(job_id, adapter.name)

    warnings = adapter.warnings()
    with BrowserController(config) as browser:
        page = browser.open_page(url)
        adapter.wait_ready(page)
        if interactive:
            print("")
            print("Browser opened. Log in or navigate manually if needed.")
            input("Press Enter here when the application form is visible and ready to scan...")

        fields = [adapter.normalize_field(field) for field in scan_page(page)]
        storage.save_detections(attempt_id, fields)
        matches = match_fields(fields, profile)
        if review_only:
            results = [
                FillResult(
                    match=match,
                    action=FillAction.SKIPPED
                    if match.confidence.value == "skip"
                    else FillAction.UNCERTAIN,
                    value_preview=match.value,
                    reason=f"Scan-only mode: {match.reason}",
                )
                for match in matches
            ]
        else:
            results = fill_matches(page, matches)
        storage.save_fill_results(attempt_id, results)
        storage.update_attempt_status(attempt_id, "scanned" if review_only else "filled")
        report = build_report(
            job_url=url,
            adapter_name=adapter.name,
            fields=fields,
            results=results,
            warnings=warnings,
        )
        report["attempt_id"] = attempt_id
        if report_path:
            write_json_report(report, report_path)
        print("")
        print(render_text_report(report))
        print(f"Attempt id: {attempt_id}")
        print("No final submit/apply/send button was clicked.")

        if keep_browser_open and interactive:
            input("Review the page manually. Press Enter to close the Playwright browser...")
        elif not keep_browser_open:
            clear_filled(page, results)

    storage.update_attempt_status(attempt_id, "reviewed", finished=True)
    return report


def scan_application(
    url: str,
    *,
    config: AppConfig,
    storage: Storage,
    profile_name: str = "default",
    report_path: str | Path | None = None,
    interactive: bool = True,
) -> dict[str, object]:
    return run_application(
        url,
        config=config,
        storage=storage,
        profile_name=profile_name,
        review_only=True,
        keep_browser_open=True,
        report_path=report_path,
        interactive=interactive,
    )
