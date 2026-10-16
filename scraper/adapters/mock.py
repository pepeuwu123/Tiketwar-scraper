"""Adapter for the mock vendor we own. This is the default and the safety net."""
import httpx
from .base import Adapter
from ..site_state import SiteState
from .. import parse

class MockAdapter(Adapter):
    def __init__(self, settings):
        super().__init__(settings)
        self.client = httpx.Client(
            base_url=settings.target_url.rstrip("/"),
            timeout=10.0,
            headers={"User-Agent": settings.user_agent},
        )

    def poll(self) -> SiteState:
        r = self.client.get("/state")
        r.raise_for_status()
        state = parse.parse_state_json(r.text)
        state.raw = {"source": "mock", "http_status": r.status_code}
        return state

    def add_to_cart(self) -> tuple[bool, str]:
        r = self.client.post("/grab")
        r.raise_for_status()
        data = r.json()
        if data.get("ok"):
            return True, f"seat {data.get('seat')} held ({data.get('seats')} left)"
        return False, f"no seat: {data}"
