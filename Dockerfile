# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DB_PATH=/data/nvd_checker.db

WORKDIR /srv/nvd-checker

COPY requirements.txt .
# Behind a TLS-inspecting corporate proxy, pass the company root CA so pip can verify PyPI:
#   docker build --secret id=corp_ca,src=certs/company-ca.pem .
RUN --mount=type=secret,id=corp_ca,required=false \
    if [ -s /run/secrets/corp_ca ]; then export PIP_CERT=/run/secrets/corp_ca; fi; \
    pip install -r requirements.txt

COPY app ./app
COPY static ./static

RUN useradd --system --uid 10001 --home-dir /srv/nvd-checker app \
    && mkdir -p /data && chown app:app /data
USER app
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"

# Exactly one worker: the NVD rate limiter and result cache live in process memory.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
