"""Browser integration tests against the local HTML fixtures.

These run headless Chromium via Playwright. They are skipped automatically if
the Chromium browser has not been installed (``python -m playwright install
chromium``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eliapplybot.filler import fill_matches
from eliapplybot.matcher import match_fields
from eliapplybot.models import Confidence, FillAction
from eliapplybot.profile_io import load_profile
from eliapplybot.review import build_report
from eliapplybot.scanner import scan_page

FIXTURES = Path(__file__).parent / "fixtures"

playwright_sync = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def browser():
    with playwright_sync.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # chromium not installed
            pytest.skip(f"Chromium unavailable: {exc}")
        yield browser
        browser.close()


@pytest.fixture()
def profile():
    return load_profile(FIXTURES / "sample_profile.json")


def open_fixture(browser, name: str):
    page = browser.new_page()
    page.goto((FIXTURES / name).resolve().as_uri())
    return page


def run_pipeline(page, profile):
    fields = scan_page(page)
    matches = match_fields(fields, profile)
    results = fill_matches(page, matches)
    return fields, matches, results


def form_values(page) -> dict[str, str]:
    return page.evaluate(
        "() => Object.fromEntries(Array.from("
        "document.querySelectorAll('input,select,textarea'))"
        ".filter(e => e.type !== 'radio' && e.type !== 'checkbox')"
        ".map(e => [e.name, e.value]))"
    )


def test_fake_application_fill_end_to_end(browser, profile):
    page = open_fixture(browser, "fake_application.html")
    fields, matches, results = run_pipeline(page, profile)

    values = form_values(page)
    assert values["first_name"] == "Eli"
    assert values["last_name"] == "Example"
    assert values["email"] == "eli@example.com"
    assert values["phone"] == "555-123-4567"
    assert values["authorized"] == "Yes"
    assert values["sponsorship"] == "No"
    assert values["education_school"] == "Example University"
    assert values["edu_start_month"] == "September"
    assert values["edu_start_year"] == "2018"
    assert values["python_years"] == "5"
    assert values["gender"] == "Decline to answer"
    assert values["veteran"] == "Decline to answer"

    # The sponsorship radio group (inside a fieldset) is answered.
    checked = page.evaluate(
        "() => Array.from(document.querySelectorAll('input:checked'))"
        ".map(e => e.name + '=' + e.value)"
    )
    assert "sponsorship_radio=no" in checked

    # Sensitive controls stay untouched.
    assert values["resume"] == ""
    assert values["cover_letter"] == ""
    assert values["why_role"] == ""
    assert page.evaluate("() => document.body.dataset.submitted") is None

    # Nothing failed, and every fill was verified.
    assert not [r for r in results if r.action == FillAction.FAILED]
    report = build_report(job_url="fixture", adapter_name="generic", fields=fields, results=results)
    assert report["required_empty_count"] == 0
    page.close()


def test_custom_combobox_and_radiogroup(browser, profile):
    page = open_fixture(browser, "custom_widgets.html")
    fields, matches, results = run_pipeline(page, profile)
    by_name = {f.name: f for f in fields if f.name}

    # Combobox inputs are detected once, as comboboxes, with their label.
    assert by_name["authorized_combo"].element_type == "combobox"
    combobox_count = sum(1 for f in fields if f.name == "authorized_combo")
    assert combobox_count == 1

    # Radio group without a fieldset still gets the question as its label.
    radio = next(f for f in fields if f.element_type == "radio")
    assert "sponsorship" in radio.label_text.lower()

    values = form_values(page)
    assert values["email"] == "eli@example.com"
    # Yes/No combobox answered by clicking the exact option.
    assert values["authorized_combo"] == "Yes"
    # EEO combobox: profile says decline; the only decline-style option is chosen.
    assert values["gender_combo"] == "Decline To Self Identify"
    checked = page.evaluate(
        "() => Array.from(document.querySelectorAll('input:checked'))"
        ".map(e => e.name + '=' + e.value)"
    )
    assert "sponsor_radio=no" in checked
    assert page.evaluate("() => document.body.dataset.submitted") is None
    page.close()


def test_combobox_without_safe_option_is_left_alone(browser, profile):
    page = open_fixture(browser, "custom_widgets.html")
    # Remove the decline option so the gender combobox has no safe match.
    page.evaluate(
        "() => document.querySelectorAll('.combo')[1].setAttribute('data-options', 'Male,Female')"
    )
    fields, matches, results = run_pipeline(page, profile)
    values = form_values(page)
    assert values["gender_combo"] == ""
    gender_results = [r for r in results if r.match.field.name == "gender_combo"]
    assert gender_results and gender_results[0].action == FillAction.UNCERTAIN
    # The dropdown was closed again.
    assert (
        page.evaluate("() => document.querySelectorAll('.combo .menu')[1].dataset.open") != "true"
    )
    page.close()


def test_submit_button_is_reported_but_never_clicked(browser, profile):
    page = open_fixture(browser, "fake_application.html")
    fields, matches, results = run_pipeline(page, profile)
    buttons = [m for m in matches if m.field.element_type == "button"]
    assert buttons
    assert all(m.confidence == Confidence.SKIP for m in buttons)
    assert any("final" in m.reason.lower() for m in buttons)
    assert page.evaluate("() => document.body.dataset.submitted") is None
    page.close()


def test_iframe_embedded_form_is_scanned_and_filled(browser, profile):
    page = open_fixture(browser, "iframe_host.html")
    page.wait_for_load_state("networkidle")
    fields, matches, results = run_pipeline(page, profile)

    frame_indexes = {f.frame_index for f in fields}
    assert len(frame_indexes) == 2, "expected fields from the host page and the iframe"

    child = page.frames[1]
    child_values = child.evaluate(
        "() => Object.fromEntries(Array.from("
        "document.querySelectorAll('input,select,textarea'))"
        ".filter(e => e.type !== 'radio' && e.type !== 'checkbox')"
        ".map(e => [e.name, e.value]))"
    )
    assert child_values["first_name"] == "Eli"
    assert child_values["email"] == "eli@example.com"
    assert child_values["authorized"] == "Yes"
    # Host-page field with no mapping stays untouched.
    assert page.locator("#referrer").input_value() == ""
    assert child.evaluate("() => document.body.dataset.submitted") is None
    assert not [r for r in results if r.action == FillAction.FAILED]
    page.close()
