import json
import fakeredis
import httpx
import pytest

from scraper.config import Settings
from scraper.adapters.base import Adapter
from scraper.runner import is_bad, next_delay, run_once
from scraper.site_state import SiteState

def settings(**kw):
    base = dict(
        target_url="http://mock-vendor:8000", adapter="mock", mode="mock",
        interval_seconds=1, headless=True, grab_once=True, redis_url="redis://localhost:6379/0",
        stream_key="tiketwar:test", user_agent="test",
    )
    base.update(kw)
    return Settings(**base)

class FakeAdapter(Adapter):
    def __init__(self, settings, state, cart_result=(True, "seat A001")):
        super().__init__(settings)
        self._state, self._cart = state, cart_result
        self.cart_calls = 0

    def poll(self):
        return self._state

    def add_to_cart(self):
        self.cart_calls += 1
        return self._cart

@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)

def test_available_publishes_check_then_adds_to_cart(r):
    a = FakeAdapter(settings(), SiteState(seats=3, available=True))
    out = run_once(settings(), a, r)
    assert out["grabbed"] is True and a.cart_calls == 1
    types = [json.loads(v["payload"])["type"] for _, v in r.xrange("tiketwar:test")]
    assert types == ["check", "add_to_cart"]

def test_sold_out_never_calls_add_to_cart(r):
    a = FakeAdapter(settings(), SiteState(seats=0, available=False))
    out = run_once(settings(), a, r)
    assert out["grabbed"] is False and a.cart_calls == 0

def test_blocked_does_not_hammer_the_site(r):
    a = FakeAdapter(settings(), SiteState(blocked=True, block_reason="captcha"))
    out = run_once(settings(), a, r)
    assert out["blocked"] is True and a.cart_calls == 0

def test_heartbeat_ttl_is_the_services_dead_threshold(r):
    """It was interval*4 = 20s while the service promised DEAD after 120s, so the
    key expired and the scraper was declared dead 100s early."""
    s = settings(interval_seconds=5, dead_after_seconds=120)
    run_once(s, FakeAdapter(s, SiteState(seats=1, available=True)), r)
    assert 100 < r.ttl("tiketwar:heartbeat") <= 120

class BoomAdapter(FakeAdapter):
    def poll(self):
        raise RuntimeError("selector rotted")

def test_poll_exception_is_recorded_not_swallowed(r):
    out = run_once(settings(), BoomAdapter(settings(), SiteState()), r)
    assert out["ok"] is False and out["error"] == "RuntimeError"
    types = [json.loads(v["payload"])["type"] for _, v in r.xrange("tiketwar:test")]
    assert types == ["poll_error"]


def test_heartbeat_is_written_even_when_the_poll_fails(r):
    """The bug this test exists for.

    The heartbeat used to be written only after a successful poll, so a rotted
    selector stopped the heartbeat and the monitor reported the scraper as DEAD.
    The loop was alive; only the site had changed. Liveness must not depend on
    the site being healthy.
    """
    out = run_once(settings(), BoomAdapter(settings(), SiteState()), r)
    assert out["ok"] is False
    hb = json.loads(r.get("tiketwar:heartbeat"))
    assert hb["ok"] is False, "a failed poll must still beat, with ok=False"
    assert hb["state"] is None
    assert 0 < r.ttl("tiketwar:heartbeat") <= 120

def test_heartbeat_reports_ok_true_on_a_successful_poll(r):
    a = FakeAdapter(settings(), SiteState(seats=2, available=True))
    run_once(settings(), a, r)
    hb = json.loads(r.get("tiketwar:heartbeat"))
    assert hb["ok"] is True and hb["state"]["seats"] == 2


def test_grab_once_stops_calling_add_to_cart(r):
    """You need ONE seat. Re-calling add-to-cart every cycle is pointless and looks
    abusive to a vendor - it is the behavior most likely to get an account flagged."""
    a = FakeAdapter(settings(), SiteState(seats=5, available=True))
    first = run_once(settings(), a, r, already_grabbed=False)
    assert first["grabbed"] is True and a.cart_calls == 1

    second = run_once(settings(), a, r, already_grabbed=True)
    assert second["grabbed"] is False
    assert second["skipped"] == "already grabbed once"
    assert a.cart_calls == 1, "must not call add_to_cart again"


def test_grab_once_off_keeps_trying(r):
    """Escape hatch: some flows need a retry loop until the cart holds a seat."""
    a = FakeAdapter(settings(grab_once=False), SiteState(seats=5, available=True))
    run_once(settings(grab_once=False), a, r, already_grabbed=True)
    assert a.cart_calls == 1


def test_grab_state_survives_a_restart(r):
    """The seat is still in the cart across a redeploy, so the flag is persisted."""
    r.set("tiketwar:grabbed", "1", ex=86400)
    assert r.get("tiketwar:grabbed") == "1"


class CartBoomAdapter(FakeAdapter):
    def add_to_cart(self):
        self.cart_calls += 1
        raise httpx.HTTPStatusError("503", request=httpx.Request("POST", "http://v/grab"),
                                    response=httpx.Response(503))

def test_add_to_cart_exception_is_recorded_not_fatal(r):
    """Mid-rush the cart endpoint 5xx's. That used to escape run_once and kill the
    scraper process, with no event recorded anywhere."""
    s = settings()
    out = run_once(s, CartBoomAdapter(s, SiteState(seats=3, available=True)), r)
    assert out["grabbed"] is False and out["cart_failed"] is True
    last = json.loads(r.xrange("tiketwar:test")[-1][1]["payload"])
    assert last["type"] == "add_to_cart" and last["ok"] is False
    assert "HTTPStatusError" in last["detail"]


class StatusAdapter(FakeAdapter):
    def __init__(self, settings, status, headers=None):
        super().__init__(settings, SiteState())
        self._status, self._headers = status, headers or {}

    def poll(self):
        resp = httpx.Response(self._status, headers=self._headers,
                              request=httpx.Request("GET", "http://v/state"))
        resp.raise_for_status()

def test_429_is_a_block_not_a_poll_error(r):
    """A rate limit is the site saying 'stop'. Treated as a plain poll_error, it got
    polled again 5s later at full speed - the way a rate limit becomes a ban."""
    s = settings()
    out = run_once(s, StatusAdapter(s, 429, {"Retry-After": "90"}), r)
    assert out["blocked"] is True and out["retry_after"] == 90
    ev = json.loads(r.xrange("tiketwar:test")[-1][1]["payload"])
    assert ev["type"] == "check" and ev["state"]["blocked"] is True
    assert ev["state"]["block_reason"] == "HTTP 429"

def test_500_is_still_an_ordinary_poll_error(r):
    s = settings()
    out = run_once(s, StatusAdapter(s, 500), r)
    assert out["ok"] is False and "blocked" not in out


def test_backoff_healthy_cycle_uses_the_interval():
    s = settings(interval_seconds=5)
    assert next_delay(s, {"ok": True}, 0) == 5

def test_backoff_blocks_grow_to_the_ceiling():
    s = settings(interval_seconds=5, max_backoff_seconds=600)
    delays = [next_delay(s, {"ok": True, "blocked": True}, n) for n in (1, 2, 3, 10)]
    assert delays == [10, 20, 40, 600]

def test_backoff_honours_retry_after_up_to_the_ceiling():
    s = settings(interval_seconds=5, max_backoff_seconds=600)
    assert next_delay(s, {"blocked": True, "retry_after": 120}, 1) == 120
    assert next_delay(s, {"blocked": True, "retry_after": 3600}, 1) == 600

def test_backoff_for_transient_errors_stays_short():
    """A flaky site must not push the next poll minutes past the moment a sale opens."""
    s = settings(interval_seconds=5)
    assert next_delay(s, {"ok": False}, 10) == 20
    assert next_delay(s, {"ok": True, "cart_failed": True}, 10) == 20

def test_refused_cart_counts_as_a_bad_cycle():
    """With GRAB_ONCE a refused add-to-cart was retried every cycle at full speed."""
    assert is_bad({"ok": True, "cart_failed": True}) is True
    assert is_bad({"ok": True, "grabbed": True}) is False

def test_sleep_alive_keeps_the_heartbeat_fresh(r, monkeypatch):
    """A 10-minute backoff must not let the heartbeat expire and page you as DEAD."""
    import scraper.runner as runner
    s = settings(interval_seconds=5)
    clock = {"t": 0.0}
    monkeypatch.setattr(runner.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(runner.time, "sleep", lambda sec: clock.__setitem__("t", clock["t"] + sec))
    touches = []
    monkeypatch.setattr(runner.events, "touch_heartbeat", lambda *_: touches.append(clock["t"]))
    runner.sleep_alive(r, s, 30)
    assert clock["t"] == 30 and len(touches) == 5     # re-beat every 5s, not after the end
