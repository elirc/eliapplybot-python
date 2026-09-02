from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from eliapplybot.models import Confidence, DetectedField, FieldMatch, FillAction, FillResult
from eliapplybot.profile_io import load_profile
from eliapplybot.storage import Storage
from eliapplybot.web.app import app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "web.sqlite3"
    monkeypatch.setenv("ELIAPPLYBOT_DB_PATH", str(db_path))
    storage = Storage(db_path)
    storage.init_db()
    storage.save_profile(load_profile(FIXTURES / "sample_profile.json"))
    job_id = storage.add_job("https://example.com/job", title="Software Engineer")
    attempt_id = storage.create_attempt(job_id, "generic")
    field = DetectedField(
        stable_id="field-1",
        selector="#email",
        element_type="input",
        input_type="email",
        label_text="Email address",
    )
    storage.save_detections(attempt_id, [field])
    match = FieldMatch(
        field=field,
        detected_field_key="email address",
        mapped_profile_key="email",
        confidence=Confidence.HIGH,
        value="eli@example.com",
        reason="Matched clear email label.",
    )
    storage.save_fill_results(
        attempt_id,
        [
            FillResult(
                match=match,
                action=FillAction.FILLED,
                value_preview="eli@example.com",
                reason="Matched clear email label.",
            )
        ],
    )
    return TestClient(app)


def test_dashboard_lists_jobs_and_attempts(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "https://example.com/job" in response.text
    assert "Software Engineer" in response.text
    assert "/attempts/1" in response.text


def test_attempt_detail_shows_masked_fill_log(client):
    response = client.get("/attempts/1")
    assert response.status_code == 200
    assert "Email address" in response.text
    # Email values are masked before they reach storage.
    assert "el***@example.com" in response.text
    assert "eli@example.com" not in response.text


def test_attempt_detail_404_for_unknown_id(client):
    assert client.get("/attempts/999").status_code == 404


def test_job_status_update_roundtrip(client):
    response = client.post("/jobs/1/status", data={"status": "applied"}, follow_redirects=True)
    assert response.status_code == 200
    assert "applied" in response.text
    assert client.post("/jobs/1/status", data={"status": "bogus"}).status_code == 400
    assert client.post("/jobs/999/status", data={"status": "applied"}).status_code == 404


def test_dictate_page_renders_answer_bank(client):
    response = client.get("/dictate")
    assert response.status_code == 200
    assert "Why this role" in response.text  # from the sample profile answer bank


def test_api_transcribe_uses_groq_and_returns_text(client, monkeypatch):
    import eliapplybot.web.app as web_app

    monkeypatch.setattr(web_app, "transcribe_audio", lambda data, filename: "Dictated answer text.")
    response = client.post(
        "/api/transcribe", files={"file": ("clip.webm", b"fake-audio", "audio/webm")}
    )
    assert response.status_code == 200
    assert response.json() == {"text": "Dictated answer text."}


def test_api_transcribe_reports_errors(client, monkeypatch):
    import eliapplybot.web.app as web_app
    from eliapplybot.transcribe import TranscriptionError

    def boom(data, filename):
        raise TranscriptionError("GROQ_API_KEY is not set.")

    monkeypatch.setattr(web_app, "transcribe_audio", boom)
    response = client.post("/api/transcribe", files={"file": ("clip.webm", b"x", "audio/webm")})
    assert response.status_code == 400
    assert "GROQ_API_KEY" in response.json()["detail"]


def test_save_answer_roundtrip(client):
    response = client.post(
        "/answers",
        data={"title": "My Strengths", "answer": "Persistence.", "tags": "strengths, about"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "my-strengths" in response.text
    assert "Persistence." in response.text
