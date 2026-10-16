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

def heartbeat(r, settings, state) -> None:
    """TTL'd key. If this expires, the scraper is dead even if the box is up."""
    ttl = max(10, int(settings.interval_seconds * 4))
    r.set("tiketwar:heartbeat", json.dumps({"ts": time.time(), "state": state.to_dict()}), ex=ttl)
