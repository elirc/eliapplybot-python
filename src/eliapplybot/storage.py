from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eliapplybot.config import ensure_parent
from eliapplybot.models import CandidateProfile, DetectedField, FillResult, JobRecord
from eliapplybot.review import mask_value

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL DEFAULT 'default',
  profile_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_name ON profiles(name);

CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL UNIQUE,
  title TEXT,
  company TEXT,
  status TEXT NOT NULL DEFAULT 'new',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS application_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL,
  adapter_name TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS field_detections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  application_attempt_id INTEGER NOT NULL,
  stable_id TEXT NOT NULL,
  field_json TEXT NOT NULL,
  detected_at TEXT NOT NULL,
  FOREIGN KEY(application_attempt_id) REFERENCES application_attempts(id)
);

CREATE TABLE IF NOT EXISTS fill_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  application_attempt_id INTEGER NOT NULL,
  field_label TEXT NOT NULL,
  field_type TEXT NOT NULL,
  detected_field_key TEXT NOT NULL,
  mapped_profile_key TEXT,
  confidence TEXT NOT NULL,
  value_preview TEXT,
  action_taken TEXT NOT NULL,
  reason TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  FOREIGN KEY(application_attempt_id) REFERENCES application_attempts(id)
);

CREATE TABLE IF NOT EXISTS review_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  application_attempt_id INTEGER NOT NULL,
  note TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(application_attempt_id) REFERENCES application_attempts(id)
);
"""


class Storage:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        ensure_parent(self.db_path)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def init_db(self) -> None:
        with self.transaction() as connection:
            connection.executescript(SCHEMA)

    def save_profile(self, profile: CandidateProfile, name: str = "default") -> int:
        now = utcnow()
        payload = profile.model_dump_json()
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT id FROM profiles WHERE name = ?", (name,)
            ).fetchone()
            if existing:
                connection.execute(
                    """
                    UPDATE profiles
                    SET profile_json = ?, updated_at = ?
                    WHERE name = ?
                    """,
                    (payload, now, name),
                )
                return int(existing["id"])
            cursor = connection.execute(
                """
                INSERT INTO profiles(name, profile_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, payload, now, now),
            )
            return int(cursor.lastrowid)

    def load_profile(self, name: str = "default") -> CandidateProfile:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT profile_json FROM profiles WHERE name = ?", (name,)
            ).fetchone()
        if not row:
            raise LookupError(f"No profile named {name!r}. Import one first.")
        return CandidateProfile.model_validate_json(row["profile_json"])

    def add_job(self, url: str, title: str | None = None, company: str | None = None) -> int:
        now = utcnow()
        with self.transaction() as connection:
            row = connection.execute("SELECT id FROM jobs WHERE url = ?", (url,)).fetchone()
            if row:
                return int(row["id"])
            cursor = connection.execute(
                """
                INSERT INTO jobs(url, title, company, status, created_at, updated_at)
                VALUES (?, ?, ?, 'new', ?, ?)
                """,
                (url, title, company, now, now),
            )
            return int(cursor.lastrowid)

    def list_jobs(self) -> list[JobRecord]:
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT id, url, title, company, status, created_at FROM jobs ORDER BY id DESC"
            ).fetchall()
        return [
            JobRecord(
                id=int(row["id"]),
                url=row["url"],
                title=row["title"],
                company=row["company"],
                status=row["status"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def create_attempt(self, job_id: int, adapter_name: str) -> int:
        now = utcnow()
        with self.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO application_attempts(job_id, adapter_name, status, started_at)
                VALUES (?, ?, 'started', ?)
                """,
                (job_id, adapter_name, now),
            )
            return int(cursor.lastrowid)

    def update_attempt_status(self, attempt_id: int, status: str, finished: bool = False) -> None:
        with self.transaction() as connection:
            if finished:
                connection.execute(
                    """
                    UPDATE application_attempts
                    SET status = ?, finished_at = ?
                    WHERE id = ?
                    """,
                    (status, utcnow(), attempt_id),
                )
            else:
                connection.execute(
                    "UPDATE application_attempts SET status = ? WHERE id = ?",
                    (status, attempt_id),
                )

    def save_detections(self, attempt_id: int, fields: Iterable[DetectedField]) -> None:
        now = utcnow()
        with self.transaction() as connection:
            connection.executemany(
                """
                INSERT INTO field_detections(
                  application_attempt_id, stable_id, field_json, detected_at
                )
                VALUES (?, ?, ?, ?)
                """,
                [(attempt_id, field.stable_id, field.model_dump_json(), now) for field in fields],
            )

    def save_fill_results(self, attempt_id: int, results: Iterable[FillResult]) -> None:
        now = utcnow()
        rows = []
        for result in results:
            match = result.match
            field = match.field
            rows.append(
                (
                    attempt_id,
                    field.label_text or field.name or field.stable_id,
                    field.input_type or field.element_type,
                    match.detected_field_key,
                    match.mapped_profile_key,
                    match.confidence.value,
                    mask_value(match.mapped_profile_key, result.value_preview),
                    result.action.value,
                    result.reason,
                    now,
                )
            )
        with self.transaction() as connection:
            connection.executemany(
                """
                INSERT INTO fill_logs(
                  application_attempt_id, field_label, field_type, detected_field_key,
                  mapped_profile_key, confidence, value_preview, action_taken, reason, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def show_attempt(self, attempt_id: int) -> dict[str, Any]:
        with self.transaction() as connection:
            attempt = connection.execute(
                """
                SELECT a.*, j.url
                FROM application_attempts a
                JOIN jobs j ON j.id = a.job_id
                WHERE a.id = ?
                """,
                (attempt_id,),
            ).fetchone()
            detections = connection.execute(
                """
                SELECT field_json
                FROM field_detections
                WHERE application_attempt_id = ?
                ORDER BY id
                """,
                (attempt_id,),
            ).fetchall()
            logs = connection.execute(
                "SELECT * FROM fill_logs WHERE application_attempt_id = ? ORDER BY id",
                (attempt_id,),
            ).fetchall()
        if not attempt:
            raise LookupError(f"No application attempt with id {attempt_id}.")
        return {
            "attempt": dict(attempt),
            "fields": [json.loads(row["field_json"]) for row in detections],
            "logs": [dict(row) for row in logs],
        }


def utcnow() -> str:
    return datetime.now(UTC).isoformat()
