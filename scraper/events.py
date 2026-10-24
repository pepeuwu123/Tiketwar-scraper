"""Everything the scraper learns leaves through this module. Redis Streams, not Flask."""
import json
import time

import redis

HEARTBEAT_KEY = "tiketwar:heartbeat"

def connect(settings) -> "redis.Redis":
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)

def publish(r, settings, event_type: str, **fields) -> str:
    body = {"type": event_type, "ts": time.time(), **fields}
    return r.xadd(
        settings.stream_key,
        {"payload": json.dumps(body)},
        maxlen=settings.stream_maxlen,
        approximate=True,
    )

def heartbeat(r, settings, state, ok: bool = True) -> None:
    """TTL'd key. If this expires, the loop is not running at all.

    Written on EVERY cycle, including failed ones, on purpose. If it were only
    written after a successful poll, then a rotted selector would stop the
    heartbeat and the monitor would report "scraper DEAD" - sending you to debug
    the wrong thing. Liveness and site-health are two different questions, so
    they get two different fields:

      heartbeat present?  -> is the loop running?
      last_ok             -> did the last poll succeed?

    The TTL is the service's dead threshold. It used to be interval*4 (20s), so the
    key vanished - and the service said DEAD - long before the 120s it promised,
    and one slow poll followed by a slow add-to-cart was enough to flap it.
    """
    body = {
        "ts": time.time(),
        "ok": ok,
        "state": state.to_dict() if state is not None else None,
    }
    r.set(HEARTBEAT_KEY, json.dumps(body), ex=max(10, settings.dead_after_seconds))

def touch_heartbeat(r, settings) -> None:
    """Re-beat during a long backoff sleep: the loop is alive, just deliberately slow."""
    raw = r.get(HEARTBEAT_KEY)
    body = json.loads(raw) if raw else {"ok": None, "state": None}
    body["ts"] = time.time()
    r.set(HEARTBEAT_KEY, json.dumps(body), ex=max(10, settings.dead_after_seconds))
