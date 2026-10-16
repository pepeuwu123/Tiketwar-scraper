# Pinned on purpose: an unpinned playwright image silently upgrades Chromium and breaks selectors.
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

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
