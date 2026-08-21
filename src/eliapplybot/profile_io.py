from __future__ import annotations

import json
from pathlib import Path

from eliapplybot.models import CandidateProfile


def load_profile(path: str | Path) -> CandidateProfile:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return CandidateProfile.model_validate(data)


def profile_template() -> str:
    """Return a starter profile JSON with placeholder values to edit."""
    template = CandidateProfile.model_validate(
        {
            "first_name": "YOUR-FIRST-NAME",
            "last_name": "YOUR-LAST-NAME",
            "email": "you@example.com",
            "phone": "555-555-5555",
            "location": "City, ST",
            "address": "123 Your Street",
            "city": "Your City",
            "state": "ST",
            "country": "United States",
            "linkedin_url": "https://www.linkedin.com/in/your-handle",
            "github_url": "https://github.com/your-handle",
            "authorization": {
                "legally_authorized_us": True,
                "requires_sponsorship_now_or_future": False,
            },
            "education": [
                {
                    "school": "Your University",
                    "degree": "Bachelor of Science",
                    "field_of_study": "Your Major",
                    "start_month": 9,
                    "start_year": 2018,
                    "end_month": 6,
                    "end_year": 2022,
                }
            ],
            "experience": [
                {
                    "company": "Your Current Company",
                    "title": "Your Title",
                    "location": "Remote",
                    "start_month": 7,
                    "start_year": 2022,
                    "current": True,
                }
            ],
            "skills": ["Skill One", "Skill Two"],
            "years_of_experience": {"Python": 3},
            "documents": {"resume_path": "C:/path/to/your resume.pdf"},
            "answer_bank": [
                {
                    "id": "why-role",
                    "title": "Why this role",
                    "category": "motivation",
                    "tags": ["why", "role", "company"],
                    "answer": "Write your reusable answer here.",
                }
            ],
            "preferences": {
                "desired_roles": ["Software Engineer"],
                "remote_preference": "Remote",
                "salary_expectation": "",
            },
        }
    )
    return template.model_dump_json(indent=2)


def save_profile(profile: CandidateProfile, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
