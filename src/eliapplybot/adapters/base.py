from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from urllib.parse import urlparse

from playwright.sync_api import Page

from eliapplybot.models import DetectedField


@dataclass
class Adapter:
    name: str = "generic"
    host_patterns: tuple[str, ...] = ()
    known_label_quirks: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def matches(self, url: str) -> bool:
        hostname = urlparse(url).hostname or ""
        return any(pattern in hostname for pattern in self.host_patterns)

    def wait_ready(self, page: Page) -> None:
        with suppress(Exception):
            page.wait_for_load_state("networkidle", timeout=8000)

    def normalize_field(self, field: DetectedField) -> DetectedField:
        return field

    def warnings(self) -> list[str]:
        return list(self.limitations)
