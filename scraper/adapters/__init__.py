from .base import Adapter
from .mock import MockAdapter

def build_adapter(settings) -> Adapter:
    if settings.adapter == "mock":
        return MockAdapter(settings)
    raise ValueError(
        f"unknown adapter {settings.adapter!r} - add scraper/adapters/{settings.adapter}.py "
        "and register it here. Real-site adapters start as a copy of mock.py."
    )
