from __future__ import annotations

from eliapplybot.adapters.base import Adapter


class AshbyAdapter(Adapter):
    def __init__(self) -> None:
        super().__init__(
            name="ashby",
            host_patterns=("ashbyhq.com", "jobs.ashbyhq.com"),
            known_label_quirks=(
                "Ashby can use custom controls; ARIA widgets are detected conservatively.",
            ),
            limitations=("Custom Ashby widgets may need manual review in this first build.",),
        )
