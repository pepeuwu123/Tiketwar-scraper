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
    dead_after_seconds: int = 120
    max_backoff_seconds: float = 600
    grab_hold_seconds: int = 86400
    stream_maxlen: int = 100000

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
            # Same variable the service reads, so "heartbeat expired" and "service
            # says DEAD" happen at the same moment instead of 20s vs 120s.
            dead_after_seconds=int(os.environ.get("DEAD_AFTER_SECONDS", "120")),
            # Ceiling for slowing down after a block or a 429. Retry-After is honoured up to this.
            max_backoff_seconds=float(os.environ.get("MAX_BACKOFF_SECONDS", "600")),
            # How long a grabbed seat stays in the vendor's cart. Real carts usually let
            # go after 10-15 minutes; a 24h flag would then stop the scraper re-grabbing
            # for a day after the seat was already lost. Set this per real adapter.
            grab_hold_seconds=int(os.environ.get("GRAB_HOLD_SECONDS", "86400")),
            # Stream entries kept for the consumer. 10k was ~14h at 5s, so a consumer
            # down overnight lost events silently. 100k is ~6 days and a few tens of MB.
            stream_maxlen=int(os.environ.get("STREAM_MAXLEN", "100000")),
        )
