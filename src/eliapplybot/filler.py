from __future__ import annotations

from playwright.sync_api import Page

from eliapplybot.models import Confidence, FieldMatch, FillAction, FillResult
from eliapplybot.review import mask_value


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
            return FillResult(
                match=match,
                action=FillAction.UNCERTAIN,
                value_preview=value,
                old_value=old_value,
                reason="Custom ARIA widget detected; review and fill manually in this first build.",
            )
        elif (field.input_type or "").lower() in {"file", "submit", "button", "reset", "image"}:
            return FillResult(
                match=match,
                action=FillAction.SKIPPED,
                value_preview=value,
                old_value=old_value,
                reason="Unsafe or non-text control skipped.",
            )
        else:
            locator.fill(value, timeout=5000)
        return FillResult(
            match=match,
            action=FillAction.FILLED,
            value_preview=value,
            old_value=old_value,
            reason=match.reason,
        )
    except Exception as exc:
        return failed(match, old_value, f"Playwright fill failed: {exc}")


def clear_filled(page: Page, results: list[FillResult]) -> int:
    cleared = 0
    for result in reversed(results):
        if result.action != FillAction.FILLED:
            continue
        field = result.match.field
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
