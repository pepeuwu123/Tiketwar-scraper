# Tiketwar-scraper

Polls a ticket page, detects availability, and (optionally) adds to cart on the
**operator's own account**. It never checks out and never pays.

## Safety rules baked into the code
- `SCRAPE_MODE=mock` + `ADAPTER=mock` is the default. The whole pipeline runs
  against a mock vendor we own, with zero real traffic.
- A detected block (captcha / login wall / 429) is **flagged as `blocked`, not retried harder**.
- `parse()` is pure and tested; `SiteState.seats is None` means *unknown*, which is
  deliberately different from `0` (*sold out*). Conflating them is how a broken
  scraper hides as "nothing available".
- There is no checkout code in this repo, by design.
- `GRAB_ONCE=true` (default) adds to cart once, then keeps polling without calling
  add-to-cart again. Repeated grab calls are the fastest way to get flagged, and you
  only need one seat. The flag is persisted in redis so a restart does not re-grab.

## What is explicitly out of scope
CAPTCHA/anti-bot solving, TLS or fingerprint spoofing, proxy rotation,
multi-account use, and any checkout or payment automation.

## Run it
```sh
cp .env.example .env
pip install -e '.[dev]'
pytest
python -m scraper.runner
```

## Adding a real site
Copy `scraper/adapters/mock.py` to `scraper/adapters/<site>.py`, implement `poll()`,
register it in `scraper/adapters/__init__.py`, then set `ADAPTER=<site>`. Keep it to
one file so it can be removed in one commit.
