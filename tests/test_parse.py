from scraper.parse import parse_state_json, parse_seats_from_html

def test_json_state_available():
    s = parse_state_json('{"seats": 40, "title": "NEBULA TOUR 2026"}')
    assert s.seats == 40 and s.available is True

def test_json_state_sold_out():
    s = parse_state_json({"seats": 0})
    assert s.seats == 0 and s.available is False

def test_html_seats():
    s = parse_seats_from_html('<p id="seats">7</p>')
    assert s.seats == 7 and s.available is True

def test_html_captcha_is_flagged_as_blocked_not_retried():
    s = parse_seats_from_html("<h1>Please verify you are human</h1>")
    assert s.blocked is True and s.block_reason == "verify you are human"

def test_html_no_seats_marker_is_unknown_not_zero():
    """Unknown must not look like sold out - that's how yield decay hides."""
    s = parse_seats_from_html("<h1>Concert</h1>")
    assert s.seats is None
