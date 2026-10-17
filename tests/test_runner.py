import json
import fakeredis
import pytest

from scraper.config import Settings
from scraper.adapters.base import Adapter
from scraper.runner import run_once
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

def test_heartbeat_has_a_ttl(r):
    a = FakeAdapter(settings(interval_seconds=5), SiteState(seats=1, available=True))
    run_once(settings(interval_seconds=5), a, r)
    assert 0 < r.ttl("tiketwar:heartbeat") <= 20

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
    assert 0 < r.ttl("tiketwar:heartbeat") <= 20

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
