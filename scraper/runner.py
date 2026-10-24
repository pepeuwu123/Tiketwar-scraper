"""The loop. Deliberately dumb: poll, publish, hand off. All smartness lives in the service."""
import logging
import time

from .config import Settings
from . import events
from .adapters import build_adapter
from .site_state import SiteState

log = logging.getLogger("tiketwar.scraper")

# survives restarts so a redeploy does not re-grab a second seat
GRABBED_KEY = "tiketwar:grabbed"

# The site telling us to go away. These used to be logged as an ordinary poll_error
# and polled again 5s later at full speed - exactly what turns a rate limit into a ban.
BLOCK_STATUSES = (403, 429)

def _http_status(exc: Exception) -> int | None:
    return getattr(getattr(exc, "response", None), "status_code", None)

def _retry_after(exc: Exception) -> float | None:
    """Seconds form only. The HTTP-date form is rare on rate limits; ignore it."""
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None

def run_once(settings: Settings, adapter, r, already_grabbed: bool = False) -> dict:
    """One cycle. Returns a summary dict so the daily report can count yields."""
    try:
        state = adapter.poll()
    except Exception as exc:                      # noqa: BLE001 - we want every failure recorded
        status = _http_status(exc)
        if status in BLOCK_STATUSES:
            # A 403/429 is a block, not a broken selector: record it as one so the
            # service raises the "needs a human" alert, and tell main() to back off.
            state = SiteState(blocked=True, block_reason=f"HTTP {status}")
            log.warning("blocked: %s", state.block_reason)
            events.publish(r, settings, "check", state=state.to_dict())
            events.heartbeat(r, settings, state, ok=True)
            return {"ok": True, "blocked": True, "seats": None, "retry_after": _retry_after(exc)}
        log.warning("poll failed: %s", exc)
        events.publish(r, settings, "poll_error", error=type(exc).__name__, detail=str(exc)[:500])
        # Still beat: the loop is alive, the SITE is what broke. Reporting this as
        # a dead scraper would send you debugging the wrong component.
        events.heartbeat(r, settings, None, ok=False)
        return {"ok": False, "error": type(exc).__name__}

    events.publish(r, settings, "check", state=state.to_dict())
    events.heartbeat(r, settings, state, ok=True)

    if state.blocked:
        # Do NOT retry harder. A block means a human decides what happens next.
        log.warning("blocked: %s", state.block_reason)
        return {"ok": True, "blocked": True, "seats": state.seats}

    grabbed = False
    if state.available:
        if settings.grab_once and already_grabbed:
            # Already have a seat in the cart. Keep watching (so the heartbeat and
            # availability history stay accurate) but stop calling add-to-cart -
            # that call is the one that looks abusive to a vendor.
            return {"ok": True, "blocked": False, "seats": state.seats,
                    "grabbed": False, "skipped": "already grabbed once"}
        try:
            ok, detail = adapter.add_to_cart()
        except Exception as exc:                  # noqa: BLE001
            # Mid-rush, the cart endpoint is the one most likely to 5xx. This used to
            # escape run_once and kill the process with nothing recorded.
            ok, detail = False, f"{type(exc).__name__}: {str(exc)[:300]}"
        events.publish(r, settings, "add_to_cart", ok=ok, detail=detail, seats=state.seats)
        grabbed = ok
        log.info("add_to_cart ok=%s %s", ok, detail)
        if not ok:
            return {"ok": True, "blocked": False, "seats": state.seats,
                    "grabbed": False, "cart_failed": True}

    return {"ok": True, "blocked": False, "seats": state.seats, "grabbed": grabbed}

def is_bad(result: dict) -> bool:
    return not result.get("ok") or bool(result.get("blocked")) or bool(result.get("cart_failed"))

def next_delay(settings: Settings, result: dict, streak: int) -> float:
    """Seconds until the next poll. `streak` = consecutive bad cycles, this one included.

    Blocks back off exponentially up to max_backoff_seconds, honouring Retry-After.
    Plain poll errors and refused add-to-cart calls back off too, but capped at 4x
    the interval: those are usually transient, and missing the moment a sale opens
    is worse than a few extra requests.
    """
    base = settings.interval_seconds
    if result.get("retry_after"):
        return min(max(result["retry_after"], base), settings.max_backoff_seconds)
    if streak <= 0:
        return base
    cap = settings.max_backoff_seconds if result.get("blocked") else base * 4
    return min(base * 2 ** streak, cap)

def sleep_alive(r, settings: Settings, seconds: float) -> None:
    """Sleep in interval-sized slices, re-beating between them, so a long backoff
    is not mistaken for a dead loop."""
    end = time.monotonic() + seconds
    while (left := end - time.monotonic()) > 0:
        time.sleep(min(left, settings.interval_seconds))
        if end - time.monotonic() > 0:
            events.touch_heartbeat(r, settings)

def load_grabbed(r) -> bool:
    return r.get(GRABBED_KEY) == "1"

def mark_grabbed(r, settings: Settings) -> None:
    # survive a restart without re-grabbing, for as long as the cart holds the seat
    r.set(GRABBED_KEY, "1", ex=settings.grab_hold_seconds)

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env()
    if not settings.is_mock:
        log.warning("SCRAPE_MODE=%s - live mode: respect the site's terms and rate limits", settings.mode)
    adapter = build_adapter(settings)
    r = events.connect(settings)
    already_grabbed = load_grabbed(r)
    log.info("scraper up: target=%s adapter=%s every %ss grab_once=%s already_grabbed=%s",
             settings.target_url, settings.adapter, settings.interval_seconds,
             settings.grab_once, already_grabbed)
    streak = 0
    while True:
        started = time.monotonic()
        result = run_once(settings, adapter, r, already_grabbed=already_grabbed)
        if result.get("grabbed"):
            already_grabbed = True
            mark_grabbed(r, settings)
        streak = streak + 1 if is_bad(result) else 0
        delay = next_delay(settings, result, streak)
        if delay > settings.interval_seconds:
            log.info("backing off %.0fs (%d bad cycle(s) in a row)", delay, streak)
        sleep_alive(r, settings, max(0.0, delay - (time.monotonic() - started)))

if __name__ == "__main__":
    main()
