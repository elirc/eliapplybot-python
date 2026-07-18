from pathlib import Path

from eliapplybot.models import DetectedField
from eliapplybot.profile_io import load_profile
from eliapplybot.storage import Storage

FIXTURES = Path(__file__).parent / "fixtures"


def test_sqlite_storage_create_read_write(tmp_path):
    storage = Storage(tmp_path / "app.sqlite3")
    storage.init_db()
    profile = load_profile(FIXTURES / "sample_profile.json")
    profile_id = storage.save_profile(profile)
    assert profile_id > 0
    assert storage.load_profile().first_name == "Eli"

    job_id = storage.add_job("https://example.com/job")
    attempt_id = storage.create_attempt(job_id, "generic")
    field = DetectedField(
        stable_id="field-1",
        selector="#email",
        element_type="input",
        input_type="email",
        label_text="Email address",
    )
    storage.save_detections(attempt_id, [field])
    data = storage.show_attempt(attempt_id)
    assert data["attempt"]["adapter_name"] == "generic"
    assert data["fields"][0]["label_text"] == "Email address"
    assert storage.list_jobs()[0].url == "https://example.com/job"


def test_storage_closes_connections(tmp_path):
    db_path = tmp_path / "app.sqlite3"
    storage = Storage(db_path)
    storage.init_db()
    profile = load_profile(FIXTURES / "sample_profile.json")
    storage.save_profile(profile)
    storage.load_profile()
    job_id = storage.add_job("https://example.com/job")
    storage.create_attempt(job_id, "generic")
    storage.list_jobs()
    # On Windows this raises PermissionError if any connection is still open.
    db_path.unlink()
