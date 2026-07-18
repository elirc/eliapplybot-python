from __future__ import annotations

from eliapplybot.adapters.base import Adapter


class GenericAdapter(Adapter):
    def __init__(self) -> None:
        super().__init__(
            name="generic",
            host_patterns=(),
            known_label_quirks=(
                "Standard HTML labels, placeholders, ARIA labels, and nearby text.",
            ),
        )

    def matches(self, url: str) -> bool:
        return True
