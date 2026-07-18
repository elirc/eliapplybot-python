from __future__ import annotations

from eliapplybot.adapters.base import Adapter


class GreenhouseAdapter(Adapter):
    def __init__(self) -> None:
        super().__init__(
            name="greenhouse",
            host_patterns=("greenhouse.io", "boards.greenhouse.io"),
            known_label_quirks=(
                "Greenhouse often uses clear labels for contact, resume, and demographic sections.",
            ),
            limitations=(
                "Demographic sections remain review-first and require exact option matches.",
            ),
        )
