"""Tests for the optional Groq Whisper transcription feature.

All tests mock the Groq HTTP call — no network access and no API key needed.
"""

from pathlib import Path

import httpx
import pytest

from eliapplybot import transcribe as transcribe_module
from eliapplybot.profile_io import load_profile
from eliapplybot.storage import Storage
from eliapplybot.transcribe import (
    DEFAULT_MODEL,
    TranscriptionError,
    slugify,
    transcribe_audio,
    transcribe_file,
)

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_missing_api_key_gives_setup_instructions(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(TranscriptionError, match="console.groq.com"):
        transcribe_audio(b"audio", "clip.webm")


def test_transcribe_audio_posts_model_and_returns_text(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        captured.update(url=url, headers=headers, data=data, files=files)
        return FakeResponse(payload={"text": "  I love building useful tools.  "})

    monkeypatch.setattr(transcribe_module.httpx, "post", fake_post)
    text = transcribe_audio(b"fake-bytes", "clip.webm", api_key="test-key")
    assert text == "I love building useful tools."
    assert captured["data"]["model"] == DEFAULT_MODEL
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["files"]["file"][0] == "clip.webm"


def test_model_env_override(monkeypatch):
    monkeypatch.setenv("ELIAPPLYBOT_STT_MODEL", "whisper-large-v3")
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(payload={"text": "hi"})

    monkeypatch.setattr(transcribe_module.httpx, "post", fake_post)
    transcribe_audio(b"x", "a.wav", api_key="k")
    assert captured["data"]["model"] == "whisper-large-v3"


def test_api_error_and_empty_transcript_raise(monkeypatch):
    monkeypatch.setattr(
        transcribe_module.httpx,
        "post",
        lambda *a, **k: FakeResponse(status_code=429, text="rate limited"),
    )
    with pytest.raises(TranscriptionError, match="429"):
        transcribe_audio(b"x", "a.wav", api_key="k")

    monkeypatch.setattr(
        transcribe_module.httpx, "post", lambda *a, **k: FakeResponse(payload={"text": "  "})
    )
    with pytest.raises(TranscriptionError, match="empty transcript"):
        transcribe_audio(b"x", "a.wav", api_key="k")


def test_network_failure_is_wrapped(monkeypatch):
    def fake_post(*a, **k):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(transcribe_module.httpx, "post", fake_post)
    with pytest.raises(TranscriptionError, match="Could not reach"):
        transcribe_audio(b"x", "a.wav", api_key="k")


def test_size_and_empty_guards():
    with pytest.raises(TranscriptionError, match="empty"):
        transcribe_audio(b"", "a.wav", api_key="k")
    with pytest.raises(TranscriptionError, match="25 MB"):
        transcribe_audio(b"x" * (26 * 1024 * 1024), "a.wav", api_key="k")


def test_transcribe_file_checks_existence_and_format(tmp_path):
    with pytest.raises(FileNotFoundError):
        transcribe_file(tmp_path / "missing.wav", api_key="k")
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    with pytest.raises(TranscriptionError, match="Unsupported audio format"):
        transcribe_file(bad, api_key="k")


def test_slugify():
    assert slugify("Why This Role?") == "why-this-role"
    assert slugify("  !!  ") == "answer"


def test_append_answer_replaces_same_id(tmp_path):
    from eliapplybot.models import AnswerBankEntry

    storage = Storage(tmp_path / "app.sqlite3")
    storage.init_db()
    storage.save_profile(load_profile(FIXTURES / "sample_profile.json"))

    entry = AnswerBankEntry(
        id="why-role", title="Why this role", category="dictated", answer="New dictated answer."
    )
    storage.append_answer(entry)
    answers = storage.load_profile().answer_bank
    assert len([a for a in answers if a.id == "why-role"]) == 1
    assert answers[-1].answer == "New dictated answer."

    other = AnswerBankEntry(id="strengths", title="Strengths", category="dictated", answer="Grit.")
    storage.append_answer(other)
    assert len(storage.load_profile().answer_bank) == 2
