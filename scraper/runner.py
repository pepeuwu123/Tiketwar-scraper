"""The loop. Deliberately dumb: poll, publish, hand off. All smartness lives in the service."""
import logging
import time

from .config import Settings
from . import events
from .adapters import build_adapter

log = logging.getLogger("tiketwar.scraper")

# survives restarts so a redeploy does not re-grab a second seat
GRABBED_KEY = "tiketwar:grabbed"

def run_once(settings: Settings, adapter, r, already_grabbed: bool = False) -> dict:
    """One cycle. Returns a summary dict so the daily report can count yields."""
    try:
        state = adapter.poll()
    except Exception as exc:                      # noqa: BLE001 - we want every failure recorded
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
        ok, detail = adapter.add_to_cart()
        events.publish(r, settings, "add_to_cart", ok=ok, detail=detail, seats=state.seats)
        grabbed = ok
        log.info("add_to_cart ok=%s %s", ok, detail)

    return {"ok": True, "blocked": False, "seats": state.seats, "grabbed": grabbed}

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env()
    if not settings.is_mock:
        log.warning("SCRAPE_MODE=%s - live mode: respect the site's terms and rate limits", settings.mode)
    adapter = build_adapter(settings)
    r = events.connect(settings)
    # survive a restart without re-grabbing: the cart is still holding the seat
    already_grabbed = r.get(GRABBED_KEY) == "1"
    log.info("scraper up: target=%s adapter=%s every %ss grab_once=%s already_grabbed=%s",
             settings.target_url, settings.adapter, settings.interval_seconds,
             settings.grab_once, already_grabbed)
    while True:
        started = time.monotonic()
        result = run_once(settings, adapter, r, already_grabbed=already_grabbed)
        if result.get("grabbed"):
            already_grabbed = True
            r.set(GRABBED_KEY, "1", ex=86400)
        elapsed = time.monotonic() - started
        time.sleep(max(0.0, settings.interval_seconds - elapsed))

if __name__ == "__main__":
    main()
