# Start slim on purpose.
#
# The only adapters that exist use httpx, not a browser, so the Playwright image
# (~2 GB) buys you nothing today - and it is published mainly for amd64, which
# can fail on an Apple Silicon machine. Add it back the first time you write an
# adapter that actually needs to render JavaScript. When you do:
#
#   ARG PLAYWRIGHT_VERSION=1.47.0
#   FROM mcr.microsoft.com/playwright/python:v${PLAYWRIGHT_VERSION}-jammy
#   RUN printf 'playwright==%s\n' "${PLAYWRIGHT_VERSION}" > /tmp/constraints.txt \
#    && pip install -c /tmp/constraints.txt .
#
# The version must appear in BOTH places: the image ships browser binaries, and
# the python package has to match them exactly.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

COPY scraper ./scraper

RUN useradd -m -u 10001 scraper && chown -R scraper:scraper /app
USER scraper

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import redis,os,sys;sys.exit(0 if redis.Redis.from_url(os.environ.get('REDIS_URL','redis://redis:6379/0')).exists('tiketwar:heartbeat') else 1)"

CMD ["python", "-m", "scraper.runner"]
