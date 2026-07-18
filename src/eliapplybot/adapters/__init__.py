from eliapplybot.adapters.ashby import AshbyAdapter
from eliapplybot.adapters.base import Adapter
from eliapplybot.adapters.generic import GenericAdapter
from eliapplybot.adapters.greenhouse import GreenhouseAdapter
from eliapplybot.adapters.lever import LeverAdapter
from eliapplybot.adapters.workday import WorkdayAdapter

ADAPTERS: list[Adapter] = [
    GreenhouseAdapter(),
    LeverAdapter(),
    AshbyAdapter(),
    WorkdayAdapter(),
    GenericAdapter(),
]


def adapter_for_url(url: str) -> Adapter:
    for adapter in ADAPTERS:
        if adapter.matches(url):
            return adapter
    return GenericAdapter()
