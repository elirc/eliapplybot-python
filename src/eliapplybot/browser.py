from __future__ import annotations

import time
from contextlib import suppress
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright

from eliapplybot.config import AppConfig


class BrowserController:
    def __init__(self, config: AppConfig):
        self.config = config
        self._playwright = None
        self.context: BrowserContext | None = None

    def __enter__(self) -> BrowserController:
        self._playwright = sync_playwright().start()
        Path(self.config.browser_profile_dir).mkdir(parents=True, exist_ok=True)
        self.context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.config.browser_profile_dir),
            headless=self.config.headless,
            slow_mo=80,
            args=["--disable-blink-features=AutomationControlled"],
        )
        return self

    def __exit__(self, *_exc: object) -> None:
        if self.context:
            self.context.close()
        if self._playwright:
            self._playwright.stop()

    def open_page(self, url: str, wait_seconds: float = 1.5) -> Page:
        if not self.context:
            raise RuntimeError("BrowserController must be used as a context manager.")
        page = self.context.pages[0] if self.context.pages else self.context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        with suppress(Exception):
            page.wait_for_load_state("networkidle", timeout=8000)
        time.sleep(wait_seconds)
        return page
