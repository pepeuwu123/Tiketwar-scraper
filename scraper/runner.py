"""The loop. Deliberately dumb: poll, publish, hand off. All smartness lives in the service."""
import logging
import time

from .config import Settings
from . import events
from .adapters import build_adapter

log = logging.getLogger("tiketwar.scraper")

def run_once(settings: Settings, adapter, r) -> dict:
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
    log.info("scraper up: target=%s adapter=%s every %ss",
             settings.target_url, settings.adapter, settings.interval_seconds)
    while True:
        started = time.monotonic()
        run_once(settings, adapter, r)
        elapsed = time.monotonic() - started
        time.sleep(max(0.0, settings.interval_seconds - elapsed))

if __name__ == "__main__":
    main()
