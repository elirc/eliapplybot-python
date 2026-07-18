from __future__ import annotations

from eliapplybot.adapters.base import Adapter


class WorkdayAdapter(Adapter):
    def __init__(self) -> None:
        super().__init__(
            name="workday",
            host_patterns=("myworkdayjobs.com", "workdayjobs.com", "workday.com"),
            known_label_quirks=("Workday often renders dynamic controls and multi-step flows.",),
            limitations=(
                "Workday support is partial; login, dynamic custom widgets, and multi-page "
                "flows need manual review.",
            ),
        )
