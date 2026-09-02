"""Optional speech-to-text via the Groq Whisper API.

This is the one feature that talks to a remote service. Only the audio you
explicitly transcribe is sent to Groq; nothing else in the app leaves your
machine. Requires a free GROQ_API_KEY (https://console.groq.com) in the
environment or .env file.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import httpx

GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_MODEL = "whisper-large-v3-turbo"
MAX_BYTES = 25 * 1024 * 1024  # Groq free-tier upload limit
SUPPORTED_SUFFIXES = {
    ".flac",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".m4a",
    ".ogg",
    ".opus",
    ".wav",
    ".webm",
}


class TranscriptionError(RuntimeError):
    """Raised when transcription cannot proceed or the API rejects the request."""


def transcribe_audio(
    data: bytes,
    filename: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    language: str | None = None,
) -> str:
    api_key = api_key or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise TranscriptionError(
            "GROQ_API_KEY is not set. Create a free key at https://console.groq.com "
            "(no card needed) and add GROQ_API_KEY=... to your .env file."
        )
    if not data:
        raise TranscriptionError("The audio is empty.")
    if len(data) > MAX_BYTES:
        raise TranscriptionError(
            f"Audio is {len(data) / 1_048_576:.1f} MB; the Groq free tier accepts up to 25 MB. "
            "Record a shorter clip or compress the file."
        )
    model = model or os.getenv("ELIAPPLYBOT_STT_MODEL", DEFAULT_MODEL)
    payload: dict[str, str] = {"model": model, "response_format": "json"}
    if language:
        payload["language"] = language
    try:
        response = httpx.post(
            GROQ_TRANSCRIBE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            data=payload,
            files={"file": (filename, data)},
            timeout=120.0,
        )
    except httpx.HTTPError as exc:
        raise TranscriptionError(f"Could not reach the Groq API: {exc}") from exc
    if response.status_code != 200:
        raise TranscriptionError(f"Groq API error {response.status_code}: {response.text[:300]}")
    text = str(response.json().get("text", "")).strip()
    if not text:
        raise TranscriptionError("Groq returned an empty transcript.")
    return text


def transcribe_file(
    path: str | Path,
    *,
    api_key: str | None = None,
    model: str | None = None,
    language: str | None = None,
) -> str:
    audio_path = Path(path)
    if not audio_path.exists():
        raise FileNotFoundError(f"No audio file at {audio_path}")
    if audio_path.suffix.lower() not in SUPPORTED_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise TranscriptionError(
            f"Unsupported audio format {audio_path.suffix!r}. Supported: {supported}."
        )
    return transcribe_audio(
        audio_path.read_bytes(),
        audio_path.name,
        api_key=api_key,
        model=model,
        language=language,
    )


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "answer"
