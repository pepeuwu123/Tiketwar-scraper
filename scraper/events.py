"""Everything the scraper learns leaves through this module. Redis Streams, not Flask."""
import json
import time

import redis

def connect(settings) -> "redis.Redis":
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)

def publish(r, settings, event_type: str, **fields) -> str:
    body = {"type": event_type, "ts": time.time(), **fields}
    return r.xadd(
        settings.stream_key,
        {"payload": json.dumps(body)},
        maxlen=10000,
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
    """
    ttl = max(10, int(settings.interval_seconds * 4))
    body = {
        "ts": time.time(),
        "ok": ok,
        "state": state.to_dict() if state is not None else None,
    }
    r.set("tiketwar:heartbeat", json.dumps(body), ex=ttl)
