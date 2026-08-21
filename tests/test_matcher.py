from pathlib import Path

from eliapplybot.matcher import match_field
from eliapplybot.models import Confidence, DetectedField
from eliapplybot.profile_io import load_profile

FIXTURES = Path(__file__).parent / "fixtures"


def field(label, *, input_type="text", element_type="input", options=None, required=False):
    return DetectedField(
        stable_id="test",
        selector="#test",
        element_type=element_type,
        input_type=input_type,
        label_text=label,
        options=options or [],
        required=required,
    )


def test_common_contact_fields_match_high_confidence():
    profile = load_profile(FIXTURES / "sample_profile.json")
    assert match_field(field("First name"), profile).mapped_profile_key == "first_name"
    email = match_field(field("Email address", input_type="email"), profile)
    assert email.confidence == Confidence.HIGH
    assert email.value == "eli@example.com"


def test_resume_cover_letter_and_submit_are_not_auto_filled():
    profile = load_profile(FIXTURES / "sample_profile.json")
    resume = match_field(field("Resume upload", input_type="file"), profile)
    assert resume.confidence == Confidence.MEDIUM
    assert resume.mapped_profile_key == "documents.resume_path"

    cover = match_field(
        field("Cover letter", element_type="textarea", input_type="textarea"), profile
    )
    assert cover.confidence == Confidence.MEDIUM

    submit = match_field(
        field("Submit application", input_type="submit", element_type="button"), profile
    )
    assert submit.confidence == Confidence.SKIP


def test_authorization_and_sponsorship_match_yes_no_options():
    profile = load_profile(FIXTURES / "sample_profile.json")
    auth = match_field(
        field("Are you legally authorized to work in the United States?", options=["Yes", "No"]),
        profile,
    )
    sponsor = match_field(
        field("Will you now or in the future require visa sponsorship?", options=["Yes", "No"]),
        profile,
    )
    assert auth.value == "Yes"
    assert sponsor.value == "No"
    assert auth.confidence == sponsor.confidence == Confidence.HIGH


def test_years_of_experience_requires_exact_skill_match():
    profile = load_profile(FIXTURES / "sample_profile.json")
    python = match_field(field("Years of Python experience", input_type="number"), profile)
    unknown = match_field(field("Years of Go experience", input_type="number"), profile)
    assert python.value == "5"
    assert python.confidence == Confidence.HIGH
    assert unknown.confidence == Confidence.MEDIUM


def test_linkedin_and_github_word_boundaries():
    profile = load_profile(FIXTURES / "sample_profile.json")
    linkedin = match_field(field("LinkedIn profile", input_type="url"), profile)
    assert linkedin.mapped_profile_key == "linkedin_url"
    assert linkedin.confidence == Confidence.HIGH

    github = match_field(field("Git Hub", input_type="url"), profile)
    assert github.mapped_profile_key == "github_url"

    unrelated = match_field(field("Legit hub count", input_type="number"), profile)
    assert unrelated.mapped_profile_key != "github_url"


def test_text_field_near_resume_wording_is_not_skipped():
    profile = load_profile(FIXTURES / "sample_profile.json")
    linkedin = DetectedField(
        stable_id="test",
        selector="#linkedin",
        element_type="input",
        input_type="url",
        label_text="LinkedIn profile",
        nearby_text="Attach your resume and share your LinkedIn profile",
    )
    match = match_field(linkedin, profile)
    assert match.mapped_profile_key == "linkedin_url"
    assert match.confidence == Confidence.HIGH


def test_long_answer_textarea_suggests_answer_bank():
    profile = load_profile(FIXTURES / "sample_profile.json")
    why = match_field(
        field(
            "Why do you want this role at our company?",
            element_type="textarea",
            input_type="textarea",
        ),
        profile,
    )
    assert why.mapped_profile_key == "answer_bank.why-role"
    assert why.confidence == Confidence.MEDIUM
    assert why.value


def labeled_field(label, nearby, *, element_type="input", input_type="text", options=None):
    return DetectedField(
        stable_id="test",
        selector="#test",
        element_type=element_type,
        input_type=input_type,
        label_text=label,
        nearby_text=nearby,
        options=options or [],
    )


def test_sibling_question_text_does_not_leak_into_match():
    profile = load_profile(FIXTURES / "sample_profile.json")
    section = (
        "Work Authorization "
        "Are you legally authorized to work in the United States? "
        "Will you now or in the future require visa sponsorship?"
    )
    sponsorship = match_field(
        labeled_field(
            "Will you now or in the future require visa sponsorship?",
            section,
            element_type="select",
            input_type="select-one",
            options=["Yes", "No"],
        ),
        profile,
    )
    assert sponsorship.mapped_profile_key == "authorization.requires_sponsorship_now_or_future"
    assert sponsorship.value == "No"


def test_education_and_experience_fields_use_own_labels():
    profile = load_profile(FIXTURES / "sample_profile.json")
    education_section = "Education School / University Degree Field of study"
    degree = match_field(labeled_field("Degree", education_section), profile)
    assert degree.mapped_profile_key == "education.0.degree"
    assert degree.value == "Bachelor of Science"

    experience_section = (
        "Experience Company / Employer Position title "
        "Years of Python experience Years of React experience"
    )
    company = match_field(labeled_field("Company / Employer", experience_section), profile)
    assert company.mapped_profile_key == "experience.0.company"
    assert company.value == "Example Co"

    react = match_field(
        labeled_field("Years of React experience", experience_section, input_type="number"),
        profile,
    )
    assert react.mapped_profile_key == "years_of_experience.React"
    assert react.value == "4"


def test_eeo_fields_use_own_labels():
    profile = load_profile(FIXTURES / "sample_profile.json")
    eeo_section = "EEO Gender Veteran status"
    veteran = match_field(
        labeled_field(
            "Veteran status",
            eeo_section,
            element_type="select",
            input_type="select-one",
            options=["Decline to answer", "I am not a protected veteran"],
        ),
        profile,
    )
    assert veteran.mapped_profile_key == "eeo.veteran_status"
    assert veteran.value == "Decline to answer"


def test_eeo_exact_option_matching():
    profile = load_profile(FIXTURES / "sample_profile.json")
    gender = match_field(
        field("Gender", element_type="select", options=["Woman", "Decline to answer"]), profile
    )
    assert gender.confidence == Confidence.HIGH
    assert gender.value == "Decline to answer"


def test_decline_synonym_matches_single_decline_option():
    profile = load_profile(FIXTURES / "sample_profile.json")
    veteran = match_field(
        field(
            "Veteran status",
            element_type="select",
            options=[
                "I am not a protected veteran",
                "I identify as a protected veteran",
                "I don't wish to answer",
            ],
        ),
        profile,
    )
    assert veteran.confidence == Confidence.HIGH
    assert veteran.value == "I don't wish to answer"


def test_eeo_combobox_without_options_is_high_only_for_decline():
    profile = load_profile(FIXTURES / "sample_profile.json")
    gender = match_field(field("Gender", element_type="combobox", input_type="combobox"), profile)
    assert gender.confidence == Confidence.HIGH
    assert gender.value == "Decline to answer"

    profile_active = profile.model_copy(deep=True)
    profile_active.eeo.gender = "Woman"
    gender_active = match_field(
        field("Gender", element_type="combobox", input_type="combobox"), profile_active
    )
    assert gender_active.confidence == Confidence.MEDIUM


def test_ambiguous_personal_labels_stay_medium():
    profile = load_profile(FIXTURES / "sample_profile.json")
    line2 = match_field(field("Address line 2"), profile)
    assert line2.confidence == Confidence.MEDIUM

    phone_type = match_field(
        field("Phone type", element_type="select", options=["Home", "Mobile"]), profile
    )
    assert phone_type.confidence == Confidence.MEDIUM

    country_code = match_field(field("Country code"), profile)
    assert country_code.confidence == Confidence.MEDIUM

    preferred_location = match_field(field("Preferred work location"), profile)
    assert preferred_location.confidence != Confidence.HIGH


def test_right_to_work_phrasing_matches_authorization():
    profile = load_profile(FIXTURES / "sample_profile.json")
    match = match_field(
        field("Do you have the right to work in the United States?", options=["Yes", "No"]),
        profile,
    )
    assert match.mapped_profile_key == "authorization.legally_authorized_us"
    assert match.value == "Yes"


def test_remote_preference_is_suggested_not_filled():
    profile = load_profile(FIXTURES / "sample_profile.json")
    match = match_field(
        field(
            "Preferred work setting",
            element_type="radio",
            input_type="radio",
            options=["Remote", "Hybrid", "On-site"],
        ),
        profile,
    )
    assert match.mapped_profile_key == "preferences.remote_preference"
    assert match.confidence == Confidence.MEDIUM
    assert match.value == "Remote or hybrid"
