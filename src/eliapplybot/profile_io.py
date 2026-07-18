from __future__ import annotations

import json
from pathlib import Path

from eliapplybot.models import CandidateProfile


def load_profile(path: str | Path) -> CandidateProfile:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return CandidateProfile.model_validate(data)


def save_profile(profile: CandidateProfile, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
