from __future__ import annotations

import re
from collections.abc import Callable

from eliapplybot.models import CandidateProfile, Confidence, DetectedField, FieldMatch

YES_OPTIONS = {"yes", "y", "true"}
NO_OPTIONS = {"no", "n", "false"}
FINAL_BUTTON_PATTERNS = re.compile(
    r"\b(submit|send|finish|complete application|apply now|final|continue to submit)\b", re.I
)
SKIP_UPLOAD_PATTERNS = re.compile(
    r"\b(resume|cv|cover letter|writing sample|attachment|portfolio upload|file upload)\b", re.I
)
LONG_ANSWER_PATTERNS = re.compile(
    r"\b(why|tell us|describe|story|project|essay|cover letter|additional information)\b", re.I
)


def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+# ]+", " ", (value or "").lower())).strip()


def field_text(field: DetectedField) -> str:
    return normalize_text(
        " ".join(
            [
                field.label_text,
                field.nearby_text,
                field.section_text,
                field.name or "",
                field.id_attribute or "",
                field.autocomplete or "",
                field.placeholder or "",
                " ".join(field.options),
            ]
        )
    )


def match_fields(fields: list[DetectedField], profile: CandidateProfile) -> list[FieldMatch]:
    return [match_field(field, profile) for field in fields]


def match_field(field: DetectedField, profile: CandidateProfile) -> FieldMatch:
    text = field_text(field)
    label = normalize_text(
        " ".join(
            [field.label_text, field.name or "", field.id_attribute or "", field.placeholder or ""]
        )
    )
    base = {"field": field, "detected_field_key": stable_key(field)}

    if field.element_type == "button" or (field.input_type or "").lower() in {
        "submit",
        "button",
        "reset",
        "image",
    }:
        reason = (
            "Final and navigation buttons are detected for review but never clicked automatically."
        )
        if FINAL_BUTTON_PATTERNS.search(text):
            reason = "Possible final application button detected; human confirmation is required."
        return FieldMatch(**base, confidence=Confidence.SKIP, reason=reason)

    is_file_input = (field.input_type or "").lower() == "file"
    if is_file_input or (field.element_type != "textarea" and SKIP_UPLOAD_PATTERNS.search(label)):
        mapped = "documents.resume_path" if re.search(r"\b(resume|cv)\b", text) else None
        value = profile.documents.resume_path if mapped else None
        if mapped and value:
            return FieldMatch(
                **base,
                mapped_profile_key=mapped,
                confidence=Confidence.MEDIUM,
                value=value,
                reason=(
                    "Resume upload found. Local path is shown for review; it is not "
                    "uploaded automatically."
                ),
            )
        return FieldMatch(
            **base,
            mapped_profile_key=mapped,
            confidence=Confidence.SKIP,
            reason="File upload or attachment field is skipped unless reviewed manually.",
        )

    if field.element_type == "textarea" and LONG_ANSWER_PATTERNS.search(text):
        answer = match_answer_bank(label if label else text, profile)
        if answer:
            return FieldMatch(
                **base,
                mapped_profile_key=f"answer_bank.{answer.id}",
                confidence=Confidence.MEDIUM,
                value=answer.answer,
                reason=(
                    f"Possible reusable answer-bank match: {answer.title}. Review before filling."
                ),
            )
        return FieldMatch(
            **base,
            confidence=Confidence.MEDIUM,
            reason=(
                "Long-form or job-specific answer found. Review and write manually or "
                "use answer bank."
            ),
        )

    for matcher in (
        match_personal,
        match_authorization,
        match_eeo,
        match_experience_years,
        match_education,
        match_experience,
        match_preferences,
    ):
        result = matcher(field, profile, text, label)
        if result:
            return FieldMatch(**base, **result)

    return FieldMatch(
        **base,
        confidence=Confidence.LOW,
        reason="No deterministic mapping matched this field.",
    )


def match_personal(
    field: DetectedField, profile: CandidateProfile, text: str, label: str
) -> dict[str, object] | None:
    rules: list[tuple[re.Pattern[str], str, Callable[[], str | None], str]] = [
        (
            re.compile(r"\b(first|given)\s*name\b"),
            "first_name",
            lambda: profile.first_name,
            "first name",
        ),
        (
            re.compile(r"\b(last|family|surname)\s*name\b"),
            "last_name",
            lambda: profile.last_name,
            "last name",
        ),
        (
            re.compile(r"(^name$|\bfull name\b)"),
            "full_name",
            lambda: profile.full_name,
            "full name",
        ),
        (
            re.compile(r"\b(e mail|email|email address)\b"),
            "email",
            lambda: str(profile.email),
            "email",
        ),
        (re.compile(r"\b(phone|mobile|telephone)\b"), "phone", lambda: profile.phone, "phone"),
        (
            re.compile(r"\b(linkedin|linked in)\b"),
            "linkedin_url",
            lambda: str(profile.linkedin_url),
            "LinkedIn",
        ),
        (
            re.compile(r"\b(github|git hub)\b"),
            "github_url",
            opt_url(profile.github_url),
            "GitHub",
        ),
        (
            re.compile(r"\b(portfolio|personal website|website|web site)\b"),
            "portfolio_url",
            opt_url(profile.portfolio_url or profile.personal_website),
            "portfolio or website",
        ),
        (re.compile(r"\baddress\b"), "address", lambda: profile.address, "address"),
        (re.compile(r"\bcity\b"), "city", lambda: profile.city, "city"),
        (re.compile(r"\bstate\b"), "state", lambda: profile.state, "state"),
        (re.compile(r"\bcountry\b"), "country", lambda: profile.country, "country"),
        (re.compile(r"\blocation\b"), "location", lambda: profile.location, "location"),
    ]
    haystack = label if label else text
    for pattern, key, getter, name in rules:
        if pattern.search(haystack):
            value = getter()
            if value:
                return high(key, value, f"Matched clear {name} label.")
            return medium(key, f"Matched {name}, but profile value is empty.")
    return None


def match_authorization(
    field: DetectedField, profile: CandidateProfile, text: str, label: str
) -> dict[str, object] | None:
    # Check the field's own label before surrounding text, so one question's
    # wording cannot leak into a sibling field in the same section.
    for haystack in dict.fromkeys([label, text]):
        if not haystack:
            continue
        if re.search(r"\b(legally authorized|authorized to work|eligible to work)\b", haystack):
            value = "Yes" if profile.authorization.legally_authorized_us else "No"
            return yes_no_match(
                field, "authorization.legally_authorized_us", value, "work authorization"
            )
        if re.search(r"\b(sponsorship|visa sponsorship|work visa)\b", haystack) and re.search(
            r"\b(require|need|now|future)\b", haystack
        ):
            value = "Yes" if profile.authorization.requires_sponsorship_now_or_future else "No"
            return yes_no_match(
                field,
                "authorization.requires_sponsorship_now_or_future",
                value,
                "sponsorship requirement",
            )
    return None


def match_eeo(
    field: DetectedField, profile: CandidateProfile, text: str, label: str
) -> dict[str, object] | None:
    if not field.options:
        return None
    haystack = label if label else text
    checks = [
        (re.compile(r"\bgender\b"), "eeo.gender", profile.eeo.gender),
        (
            re.compile(r"\b(race|ethnicity|hispanic|latino)\b"),
            "eeo.race_ethnicity",
            profile.eeo.race_ethnicity,
        ),
        (
            re.compile(r"\b(veteran|protected veteran)\b"),
            "eeo.veteran_status",
            profile.eeo.veteran_status,
        ),
        (
            re.compile(r"\b(disability|disabled)\b"),
            "eeo.disability_status",
            profile.eeo.disability_status,
        ),
    ]
    for pattern, key, value in checks:
        if pattern.search(haystack):
            if value and option_matches(field, value):
                return high(key, value, "Matched EEO field with exact available option.")
            return medium(key, "EEO field found, but saved value does not exactly match options.")
    return None


def match_experience_years(
    _field: DetectedField, profile: CandidateProfile, text: str, label: str
) -> dict[str, object] | None:
    haystack = label if label else text
    if not re.search(r"\b(years?|yrs?)\b", haystack) or not re.search(
        r"\b(experience|exp)\b", haystack
    ):
        return None
    for skill, years in profile.years_of_experience.items():
        normalized_skill = normalize_text(skill)
        if normalized_skill and re.search(rf"\b{re.escape(normalized_skill)}\b", haystack):
            return high(
                f"years_of_experience.{skill}",
                str(years),
                f"Matched exact years-of-experience skill: {skill}.",
            )
    return medium(
        "years_of_experience", "Years-of-experience field found with no exact skill match."
    )


def match_education(
    _field: DetectedField, profile: CandidateProfile, text: str, label: str
) -> dict[str, object] | None:
    if not profile.education or not re.search(
        r"\b(education|school|university|college|degree|study)\b", text
    ):
        return None
    # Section text establishes education context; the specific sub-field must
    # come from the field's own label so sibling labels cannot leak in.
    haystack = label if label else text
    edu = profile.education[0]
    if re.search(r"\b(school|university|college|institution)\b", haystack):
        return high("education.0.school", edu.school, "Matched education school field.")
    if re.search(r"\b(degree|qualification)\b", haystack):
        return high("education.0.degree", edu.degree, "Matched education degree field.")
    if re.search(r"\b(field of study|major|discipline)\b", haystack) and edu.field_of_study:
        return high(
            "education.0.field_of_study", edu.field_of_study, "Matched education field of study."
        )
    if re.search(r"\b(start|from)\b", haystack) and re.search(r"\b(date|month|year)\b", haystack):
        return high(
            "education.0.start",
            format_month_year(edu.start_month, edu.start_year),
            "Matched education start date.",
        )
    if re.search(r"\b(end|to|graduation|graduate)\b", haystack) and re.search(
        r"\b(date|month|year)\b", haystack
    ):
        return high(
            "education.0.end",
            "Present" if edu.current else format_month_year(edu.end_month, edu.end_year),
            "Matched education end date.",
        )
    return None


def match_experience(
    _field: DetectedField, profile: CandidateProfile, text: str, label: str
) -> dict[str, object] | None:
    if not profile.experience or not re.search(
        r"\b(experience|employment|employer|company|job|work history|position)\b", text
    ):
        return None
    haystack = label if label else text
    exp = profile.experience[0]
    if re.search(r"\b(company|employer|organization)\b", haystack):
        return high("experience.0.company", exp.company, "Matched work experience company field.")
    if re.search(r"\b(title|position|role)\b", haystack):
        return high("experience.0.title", exp.title, "Matched work experience title field.")
    if re.search(r"\b(location|city)\b", haystack) and exp.location:
        return high(
            "experience.0.location", exp.location, "Matched work experience location field."
        )
    if re.search(r"\b(start|from)\b", haystack) and re.search(r"\b(date|month|year)\b", haystack):
        return high(
            "experience.0.start",
            format_month_year(exp.start_month, exp.start_year),
            "Matched work experience start date.",
        )
    if re.search(r"\b(end|to)\b", haystack) and re.search(r"\b(date|month|year)\b", haystack):
        return high(
            "experience.0.end",
            "Present" if exp.current else format_month_year(exp.end_month, exp.end_year),
            "Matched work experience end date.",
        )
    return None


def match_preferences(
    _field: DetectedField, profile: CandidateProfile, text: str, _label: str
) -> dict[str, object] | None:
    if re.search(r"\b(salary|compensation|pay expectation)\b", text):
        if profile.preferences.salary_expectation:
            return medium(
                "preferences.salary_expectation",
                "Salary expectation is configured but requires review before filling.",
            )
        return medium("preferences.salary_expectation", "Salary field found; no configured value.")
    return None


def high(key: str, value: str, reason: str) -> dict[str, object]:
    return {
        "mapped_profile_key": key,
        "confidence": Confidence.HIGH,
        "value": value,
        "reason": reason,
    }


def medium(key: str, reason: str) -> dict[str, object]:
    return {
        "mapped_profile_key": key,
        "confidence": Confidence.MEDIUM,
        "reason": reason,
    }


def yes_no_match(field: DetectedField, key: str, value: str, label: str) -> dict[str, object]:
    if field.options and not option_matches(field, value):
        return medium(key, f"Matched {label}, but options are not a clear exact yes/no match.")
    return high(key, value, f"Matched clear {label} yes/no field.")


def option_matches(field: DetectedField, value: str) -> bool:
    normalized = normalize_text(value)
    return any(normalize_text(option) == normalized for option in field.options)


def stable_key(field: DetectedField) -> str:
    return normalize_text(field.label_text or field.name or field.id_attribute or field.stable_id)


def format_month_year(month: int | None, year: int | None) -> str:
    if not year:
        return ""
    if not month:
        return str(year)
    return f"{month:02d}/{year}"


def opt_url(value: object | None) -> Callable[[], str | None]:
    return lambda: str(value) if value else None


def match_answer_bank(text: str, profile: CandidateProfile):
    tokens = set(text.split())
    best = None
    best_score = 0
    for entry in profile.answer_bank:
        entry_tokens = {normalize_text(tag) for tag in entry.tags} | set(
            normalize_text(entry.title).split()
        )
        score = len(tokens & entry_tokens)
        if score > best_score:
            best = entry
            best_score = score
    return best if best_score >= 2 else None
