from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    root_dir: Path
    db_path: Path
    browser_profile_dir: Path
    headless: bool = False

    @classmethod
    def from_env(cls) -> AppConfig:
        load_dotenv()
        root = Path.cwd()
        db_path = Path(os.getenv("ELIAPPLYBOT_DB_PATH", "data/eliapplybot.sqlite3"))
        profile = Path(os.getenv("ELIAPPLYBOT_BROWSER_PROFILE", "playwright-profile"))
        headless = os.getenv("ELIAPPLYBOT_HEADLESS", "false").lower() in {"1", "true", "yes"}
        return cls(
            root_dir=root,
            db_path=db_path if db_path.is_absolute() else root / db_path,
            browser_profile_dir=profile if profile.is_absolute() else root / profile,
            headless=headless,
        )


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
