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
        interval_seconds=1, headless=True, redis_url="redis://localhost:6379/0",
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
