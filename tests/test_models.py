from pathlib import Path

import pytest
from pydantic import ValidationError

from eliapplybot.profile_io import load_profile, save_profile

FIXTURES = Path(__file__).parent / "fixtures"


def test_candidate_profile_validation_and_full_name(tmp_path):
    profile = load_profile(FIXTURES / "sample_profile.json")
    assert profile.full_name == "Eli Example"
    assert profile.education[0].school == "Example University"

    exported = tmp_path / "profile.json"
    save_profile(profile, exported)
    round_trip = load_profile(exported)
    assert round_trip.email == profile.email


def test_candidate_profile_rejects_unknown_fields():
    data = (FIXTURES / "sample_profile.json").read_text(encoding="utf-8")
    profile = load_profile(FIXTURES / "sample_profile.json").model_dump()
    profile["unknown"] = "nope"
    with pytest.raises(ValidationError):
        load_profile_from_dict(profile)
    assert "eli@example.com" in data


def load_profile_from_dict(data):
    from eliapplybot.models import CandidateProfile

    return CandidateProfile.model_validate(data)
