"""All tunables come from the environment. No site details hardcoded."""
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    target_url: str
    adapter: str          # "mock" | "generic"
    mode: str             # "mock" | "live"
    interval_seconds: float
    headless: bool
    grab_once: bool
    redis_url: str
    stream_key: str
    user_agent: str

    @property
    def is_mock(self) -> bool:
        return self.mode == "mock"

    @staticmethod
    def from_env() -> "Settings":
        return Settings(
            target_url=os.environ.get("TARGET_URL", "http://mock-vendor:8000"),
            adapter=os.environ.get("ADAPTER", "mock"),
            mode=os.environ.get("SCRAPE_MODE", "mock"),
            interval_seconds=float(os.environ.get("INTERVAL_SECONDS", "5")),
            headless=os.environ.get("HEADLESS", "true").lower() == "true",
            # You want ONE seat. Repeatedly calling add-to-cart is both pointless and
            # the fastest way to get an account flagged, so this is on by default.
            grab_once=os.environ.get("GRAB_ONCE", "true").lower() == "true",
            redis_url=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
            stream_key=os.environ.get("STREAM_KEY", "tiketwar:events"),
            user_agent=os.environ.get("USER_AGENT", "Tiketwar-Monitor/0.1 (+personal use)"),
        )
