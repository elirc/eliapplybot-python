from __future__ import annotations

import re
from contextlib import suppress

from playwright.sync_api import Page

from eliapplybot.matcher import is_decline, normalize_text
from eliapplybot.models import Confidence, FieldMatch, FillAction, FillResult
from eliapplybot.review import mask_value

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def fill_matches(page: Page, matches: list[FieldMatch]) -> list[FillResult]:
    results: list[FillResult] = []
    for match in matches:
        if match.confidence != Confidence.HIGH:
            action = (
                FillAction.SKIPPED if match.confidence == Confidence.SKIP else FillAction.UNCERTAIN
            )
            results.append(
                FillResult(
                    match=match,
                    action=action,
                    value_preview=match.value,
                    reason=match.reason,
                )
            )
            continue
        result = fill_one(page, match)
        results.append(result)
    return results


def fill_one(page: Page, match: FieldMatch) -> FillResult:
    field = match.field
    value = match.value or ""
    try:
        frame = page.frames[field.frame_index]
    except IndexError:
        return FillResult(
            match=match,
            action=FillAction.FAILED,
            value_preview=mask_value(match.mapped_profile_key, value),
            reason="Frame disappeared before filling.",
        )

    locator = frame.locator(field.selector).first
    old_value = field.current_value
    try:
        if field.element_type == "select":
            if not select_exact(locator, value):
                return failed(match, old_value, "No exact select option matched the profile value.")
        elif field.element_type in {"radio", "checkbox"}:
            if not choose_exact(frame, field.selector, value):
                return failed(
                    match, old_value, "No exact radio/checkbox option matched the profile value."
                )
        elif field.element_type in {"combobox", "listbox"}:
            return fill_combobox(frame, locator, match, old_value)
        elif (field.input_type or "").lower() in {"file", "submit", "button", "reset", "image"}:
            return FillResult(
                match=match,
                action=FillAction.SKIPPED,
                value_preview=value,
                old_value=old_value,
                reason="Unsafe or non-text control skipped.",
            )
        elif (field.input_type or "").lower() == "date" and not ISO_DATE.fullmatch(value):
            return uncertain(
                match,
                old_value,
                "Native date input needs a full YYYY-MM-DD value; fill manually.",
            )
        else:
            locator.fill(value, timeout=5000)
            actual = read_back(locator)
            if actual is not None and normalize_text(actual) != normalize_text(value):
                return failed(
                    match,
                    old_value,
                    f"Verification failed: field shows {actual!r} after filling.",
                )
        return FillResult(
            match=match,
            action=FillAction.FILLED,
            value_preview=value,
            old_value=old_value,
            reason=match.reason,
        )
    except Exception as exc:
        return failed(match, old_value, f"Playwright fill failed: {exc}")


def read_back(locator) -> str | None:
    try:
        return locator.input_value(timeout=2000)
    except Exception:
        return None


def fill_combobox(frame, locator, match: FieldMatch, old_value: str | None) -> FillResult:
    """Fill a custom ARIA combobox by opening it and clicking an exact option.

    Safety rules:
    - Only exact (normalized) option-text matches are clicked, plus a single
      decline-style option when the profile value is itself decline-style.
    - If no safe option is found, the widget is closed with Escape and the
      field is reported as uncertain for manual review.
    """
    value = match.value or ""
    uncertain_reason = (
        "Custom dropdown: no option exactly matched the saved value; review and pick manually."
    )
    try:
        locator.click(timeout=4000)
        options = frame.locator("[role='option']")
        try:
            options.first.wait_for(state="visible", timeout=3000)
        except Exception:
            frame.page.keyboard.press("Escape")
            return uncertain(match, old_value, "Custom dropdown did not show options when opened.")
        texts = options.all_inner_texts()
        target_index = pick_option_index(texts, value)
        if target_index is None:
            frame.page.keyboard.press("Escape")
            return uncertain(match, old_value, uncertain_reason)
        chosen = texts[target_index].strip()
        option = options.nth(target_index)
        try:
            option.click(timeout=3000)
        except Exception:
            # Overlapping layout can block Playwright's actionability check even
            # though the option is the real, visible target we just read. The
            # option text was verified above, so a direct DOM click is safe.
            option.evaluate("el => el.click()")
        return FillResult(
            match=match,
            action=FillAction.FILLED,
            value_preview=chosen,
            old_value=old_value,
            reason=f"Selected exact custom-dropdown option: {chosen}.",
        )
    except Exception as exc:
        with suppress(Exception):
            frame.page.keyboard.press("Escape")
        return uncertain(match, old_value, f"Custom dropdown could not be filled safely: {exc}")


def pick_option_index(texts: list[str], value: str) -> int | None:
    normalized = normalize_text(value)
    for index, text in enumerate(texts):
        if normalize_text(text) == normalized:
            return index
    if is_decline(value):
        declines = [index for index, text in enumerate(texts) if is_decline(text)]
        if len(declines) == 1:
            return declines[0]
    return None


def uncertain(match: FieldMatch, old_value: str | None, reason: str) -> FillResult:
    return FillResult(
        match=match,
        action=FillAction.UNCERTAIN,
        value_preview=match.value,
        old_value=old_value,
        reason=reason,
    )


def clear_filled(page: Page, results: list[FillResult]) -> int:
    cleared = 0
    for result in reversed(results):
        if result.action != FillAction.FILLED:
            continue
        field = result.match.field
        if field.element_type in {"combobox", "listbox"}:
            continue
        try:
            frame = page.frames[field.frame_index]
            locator = frame.locator(field.selector).first
            if field.element_type == "select":
                old = result.old_value or ""
                if old and not select_exact(locator, old):
                    continue
                if not old:
                    locator.select_option(value="")
            elif field.element_type in {"radio", "checkbox"}:
                continue
            else:
                locator.fill(result.old_value or "")
            cleared += 1
        except Exception:
            continue
    return cleared


def select_exact(locator, value: str) -> bool:
    for candidate in ({"label": value}, {"value": value}):
        try:
            locator.select_option(**candidate, timeout=2000)
            return True
        except Exception:
            pass
    return False


def choose_exact(frame, selector: str, value: str) -> bool:
    return bool(
        frame.evaluate(
            r"""
            ({ selector, value }) => {
              const normalize = (raw) => (raw || "")
                .toLowerCase()
                .replace(/[^a-z0-9+# ]+/g, " ")
                .replace(/\s+/g, " ")
                .trim();
              const desired = normalize(value);
              const explicitLabel = (input) => {
                if (input.id) {
                  const label = document.querySelector(`label[for="${CSS.escape(input.id)}"]`);
                  if (label) return label.innerText || label.textContent || "";
                }
                const wrapped = input.closest("label");
                return wrapped ? wrapped.innerText || wrapped.textContent || "" : "";
              };
              for (const input of Array.from(document.querySelectorAll(selector))) {
                const candidate = normalize(explicitLabel(input) || input.value);
                if (candidate === desired) {
                  input.click();
                  input.dispatchEvent(new Event("input", { bubbles: true }));
                  input.dispatchEvent(new Event("change", { bubbles: true }));
                  return true;
                }
              }
              return false;
            }
            """,
            {"selector": selector, "value": value},
        )
    )


def failed(match: FieldMatch, old_value: str | None, reason: str) -> FillResult:
    return FillResult(
        match=match,
        action=FillAction.FAILED,
        value_preview=match.value,
        old_value=old_value,
        reason=reason,
    )
