"""Pure parsing: HTML/JSON -> SiteState. No browser, no network. Tested in tests/."""
import json
import re
from .site_state import SiteState

_SEATS_RE = re.compile(r'id=["\']seats["\'][^>]*>\s*([0-9]+)', re.I)
_BLOCK_MARKERS = ("captcha", "are you a robot", "verify you are human", "access denied", "rate limit")

def parse_seats_from_html(html: str) -> SiteState:
    """Generic HTML fallback. Real sites get their own adapter instead of growing this."""
    low = html.lower()
    for marker in _BLOCK_MARKERS:
        if marker in low:
            return SiteState(blocked=True, block_reason=marker)
    m = _SEATS_RE.search(html)
    if not m:
        return SiteState(seats=None, available=False)
    seats = int(m.group(1))
    return SiteState(seats=seats, available=seats > 0)

def parse_state_json(payload: str | dict) -> SiteState:
    """Used by the mock vendor, which returns clean JSON on purpose."""
    data = json.loads(payload) if isinstance(payload, str) else payload
    seats = data.get("seats")
    return SiteState(
        seats=seats,
        available=bool(seats and seats > 0),
        price=data.get("price"),
        title=data.get("title"),
    )
