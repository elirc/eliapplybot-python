from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from eliapplybot.models import DetectedField, FillAction, FillResult

SENSITIVE_KEYS = ("email", "phone", "address")


def mask_value(key: str | None, value: str | None) -> str | None:
    if value is None:
        return None
    lowered = (key or "").lower()
    if "email" in lowered and "@" in value:
        name, domain = value.split("@", 1)
        return f"{name[:2]}***@{domain}"
    if "phone" in lowered:
        digits = "".join(ch for ch in value if ch.isdigit())
        return f"***-***-{digits[-4:]}" if len(digits) >= 4 else "***"
    if "address" in lowered:
        return "[address configured]"
    if "resume_path" in lowered or "cover_letter_path" in lowered:
        return value
    if len(value) > 120:
        return value[:117] + "..."
    return value


def build_report(
    *,
    job_url: str,
    adapter_name: str,
    fields: list[DetectedField],
    results: list[FillResult],
    warnings: list[str] | None = None,
) -> dict[str, object]:
    counts = Counter(result.action.value for result in results)
    required_empty = [
        field
        for field in fields
        if field.required
        and not (field.current_value or "").strip()
        and not was_filled(field, results)
    ]
    final_buttons = [
        field
        for field in fields
        if field.element_type == "button"
        or (field.input_type or "").lower() in {"submit", "button"}
    ]
    return {
        "job_url": job_url,
        "ats_adapter": adapter_name,
        "total_detected_fields": len(fields),
        "filled_count": counts[FillAction.FILLED.value],
        "skipped_count": counts[FillAction.SKIPPED.value],
        "uncertain_count": counts[FillAction.UNCERTAIN.value],
        "failed_count": counts[FillAction.FAILED.value],
        "required_empty_count": len(required_empty),
        "filled_fields": [
            entry(result) for result in results if result.action == FillAction.FILLED
        ],
        "uncertain_fields": [
            entry(result) for result in results if result.action == FillAction.UNCERTAIN
        ],
        "skipped_fields": [
            entry(result) for result in results if result.action == FillAction.SKIPPED
        ],
        "failed_fields": [
            entry(result) for result in results if result.action == FillAction.FAILED
        ],
        "missing_required_fields": [field_summary(field) for field in required_empty],
        "possible_final_buttons": [field_summary(field) for field in final_buttons],
        "warnings": warnings or [],
        "final_manual_checklist": checklist(required_empty, final_buttons),
    }


def write_json_report(report: dict[str, object], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")


def render_text_report(report: dict[str, object]) -> str:
    lines = [
        "eliapplybot review report",
        f"Job URL: {report['job_url']}",
        f"Adapter: {report['ats_adapter']}",
        "",
        (
            "Counts: "
            f"detected={report['total_detected_fields']} "
            f"filled={report['filled_count']} "
            f"skipped={report['skipped_count']} "
            f"uncertain={report['uncertain_count']} "
            f"failed={report['failed_count']} "
            f"required_empty={report['required_empty_count']}"
        ),
        "",
    ]
    for title, key in [
        ("Filled", "filled_fields"),
        ("Uncertain / Review", "uncertain_fields"),
        ("Skipped", "skipped_fields"),
        ("Failed", "failed_fields"),
        ("Missing Required", "missing_required_fields"),
        ("Possible Final Buttons", "possible_final_buttons"),
    ]:
        lines.extend(section(title, report.get(key, [])))
    warnings = report.get("warnings") or []
    if warnings:
        lines.append("Warnings")
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")
    lines.append("Final Manual Checklist")
    lines.extend(f"- {item}" for item in report["final_manual_checklist"])
    return "\n".join(lines).rstrip() + "\n"


def section(title: str, rows: object) -> list[str]:
    lines = [title]
    if not rows:
        return lines + ["- none", ""]
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        label = row.get("label") or row.get("stable_id")
        reason = row.get("reason")
        value = row.get("value_preview")
        mapped = row.get("mapped_profile_key")
        suffix = f" -> {mapped}" if mapped else ""
        value_part = f" [{value}]" if value else ""
        reason_part = f": {reason}" if reason else ""
        lines.append(f"- {label}{suffix}{value_part}{reason_part}")
    lines.append("")
    return lines


def entry(result: FillResult) -> dict[str, object]:
    match = result.match
    return {
        "stable_id": match.field.stable_id,
        "label": (
            match.field.label_text
            or match.field.name
            or match.field.id_attribute
            or match.field.stable_id
        ),
        "field_type": match.field.input_type or match.field.element_type,
        "detected_field_key": match.detected_field_key,
        "mapped_profile_key": match.mapped_profile_key,
        "confidence": match.confidence.value,
        "value_preview": mask_value(match.mapped_profile_key, result.value_preview),
        "action": result.action.value,
        "reason": result.reason,
    }


def field_summary(field: DetectedField) -> dict[str, object]:
    return {
        "stable_id": field.stable_id,
        "label": field.label_text or field.name or field.id_attribute or field.stable_id,
        "field_type": field.input_type or field.element_type,
        "required": field.required,
    }


def was_filled(field: DetectedField, results: list[FillResult]) -> bool:
    return any(
        result.match.field.stable_id == field.stable_id and result.action == FillAction.FILLED
        for result in results
    )


def checklist(required_empty: list[DetectedField], final_buttons: list[DetectedField]) -> list[str]:
    items = [
        "Review all filled fields for accuracy before moving forward.",
        "Manually complete uncertain, skipped, and failed fields.",
        "Upload resume or cover letter manually if the report identifies those fields.",
        "Do not press final submit/apply/send until you have reviewed the whole page.",
    ]
    if required_empty:
        items.append(f"Complete {len(required_empty)} required field(s) that remain empty.")
    if final_buttons:
        items.append("Final/navigation buttons were detected and intentionally left untouched.")
    return items
