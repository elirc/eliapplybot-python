from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    SKIP = "skip"


class FillAction(StrEnum):
    FILLED = "filled"
    SKIPPED = "skipped"
    UNCERTAIN = "uncertain"
    FAILED = "failed"


class EducationEntry(BaseModel):
    school: str
    degree: str
    field_of_study: str | None = None
    start_month: int | None = Field(default=None, ge=1, le=12)
    start_year: int | None = Field(default=None, ge=1900, le=2100)
    end_month: int | None = Field(default=None, ge=1, le=12)
    end_year: int | None = Field(default=None, ge=1900, le=2100)
    current: bool = False
    gpa: str | None = None
    location: str | None = None


class ExperienceEntry(BaseModel):
    company: str
    title: str
    location: str | None = None
    start_month: int | None = Field(default=None, ge=1, le=12)
    start_year: int | None = Field(default=None, ge=1900, le=2100)
    end_month: int | None = Field(default=None, ge=1, le=12)
    end_year: int | None = Field(default=None, ge=1900, le=2100)
    current: bool = False
    description_bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class Authorization(BaseModel):
    legally_authorized_us: bool
    requires_sponsorship_now_or_future: bool
    authorized_countries: list[str] = Field(default_factory=list)
    work_authorization_notes: str | None = None


class EEO(BaseModel):
    gender: str | None = "Decline to answer"
    race_ethnicity: str | None = "Decline to answer"
    veteran_status: str | None = "Decline to answer"
    disability_status: str | None = "Decline to answer"
    decline_to_answer: bool = True


class Documents(BaseModel):
    resume_path: str | None = None
    cover_letter_path: str | None = None
    portfolio_files: list[str] = Field(default_factory=list)

    @field_validator("resume_path", "cover_letter_path")
    @classmethod
    def expand_document_path(cls, value: str | None) -> str | None:
        if not value:
            return value
        return str(Path(value).expanduser())


class AnswerBankEntry(BaseModel):
    id: str
    title: str
    category: str
    tags: list[str] = Field(default_factory=list)
    answer: str
    last_updated: date | None = None


class Preferences(BaseModel):
    desired_roles: list[str] = Field(default_factory=list)
    desired_locations: list[str] = Field(default_factory=list)
    remote_preference: str | None = None
    salary_expectation: str | None = None
    earliest_start_date: date | None = None


class CandidateProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str
    last_name: str
    full_name: str | None = None
    email: EmailStr
    phone: str
    location: str
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    linkedin_url: HttpUrl
    github_url: HttpUrl | None = None
    portfolio_url: HttpUrl | None = None
    personal_website: HttpUrl | None = None
    authorization: Authorization
    eeo: EEO = Field(default_factory=EEO)
    education: list[EducationEntry] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    years_of_experience: dict[str, int] = Field(default_factory=dict)
    documents: Documents = Field(default_factory=Documents)
    answer_bank: list[AnswerBankEntry] = Field(default_factory=list)
    preferences: Preferences = Field(default_factory=Preferences)

    @model_validator(mode="after")
    def derive_full_name(self) -> CandidateProfile:
        if not self.full_name:
            self.full_name = f"{self.first_name} {self.last_name}".strip()
        return self

    @field_validator("years_of_experience")
    @classmethod
    def validate_years(cls, value: dict[str, int]) -> dict[str, int]:
        for skill, years in value.items():
            if not skill.strip():
                raise ValueError("years_of_experience keys must be non-empty skill names")
            if years < 0 or years > 80:
                raise ValueError("years_of_experience values must be between 0 and 80")
        return value


class DetectedField(BaseModel):
    stable_id: str
    frame_index: int = 0
    frame_url: str | None = None
    selector: str
    element_type: str
    input_type: str | None = None
    label_text: str = ""
    nearby_text: str = ""
    section_text: str = ""
    name: str | None = None
    id_attribute: str | None = None
    autocomplete: str | None = None
    placeholder: str | None = None
    options: list[str] = Field(default_factory=list)
    current_value: str | None = None
    required: bool = False
    confidence_notes: list[str] = Field(default_factory=list)


class FieldMatch(BaseModel):
    field: DetectedField
    detected_field_key: str
    mapped_profile_key: str | None = None
    confidence: Confidence
    value: str | None = None
    reason: str


class FillResult(BaseModel):
    match: FieldMatch
    action: FillAction
    value_preview: str | None = None
    reason: str
    old_value: str | None = None


class JobRecord(BaseModel):
    id: int | None = None
    url: str
    title: str | None = None
    company: str | None = None
    status: str = "new"
    created_at: datetime | None = None


class ApplicationAttempt(BaseModel):
    id: int | None = None
    job_id: int
    adapter_name: str
    status: Literal["started", "scanned", "filled", "reviewed", "closed"] = "started"
    started_at: datetime | None = None


JsonDict = dict[str, Any]
