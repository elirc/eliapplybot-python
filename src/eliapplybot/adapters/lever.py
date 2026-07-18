from __future__ import annotations

from eliapplybot.adapters.base import Adapter


class LeverAdapter(Adapter):
    def __init__(self) -> None:
        super().__init__(
            name="lever",
            host_patterns=("lever.co", "jobs.lever.co"),
            known_label_quirks=(
                "Lever commonly groups resume and additional information near contact fields.",
            ),
            limitations=("Additional information textareas are suggested from answer bank only.",),
        )
