# The playwright image ships browser BINARIES at this exact version. The python
# package must match them or the browsers are invisible at launch. So the version
# lives in one variable and is used in both places - never as a bare >= anywhere.
ARG PLAYWRIGHT_VERSION=1.47.0
FROM mcr.microsoft.com/playwright/python:v${PLAYWRIGHT_VERSION}-jammy

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml ./
# Constrain rather than --no-deps: --no-deps would also skip redis and httpx,
# leaving a container that cannot publish anything. This pins playwright to the
# image's browser build while letting pip resolve the real dependencies.
RUN printf 'playwright==%s\n' "${PLAYWRIGHT_VERSION}" > /tmp/constraints.txt \
 && pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -c /tmp/constraints.txt .

COPY scraper ./scraper

RUN useradd -m -u 10001 scraper && chown -R scraper:scraper /app
USER scraper

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import redis,os,sys;sys.exit(0 if redis.Redis.from_url(os.environ.get('REDIS_URL','redis://redis:6379/0')).exists('tiketwar:heartbeat') else 1)"

CMD ["python", "-m", "scraper.runner"]
