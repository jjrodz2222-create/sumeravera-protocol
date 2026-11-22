# SumerAvera Protocol — runnable container image.
#
# Runs the protocol's own FastAPI service: GET / and POST /verify.
# The image contains no secret. Set SUMERAVERA_SECRET_KEY (at least
# 32 bytes) when you run it — the service refuses to start without one.
# State (ledger.db, nonce_cache.db) is written into /app, the working
# directory, the same as running from a checkout.
FROM python:3.12-slim

WORKDIR /app

# The protocol's only third-party dependencies are fastapi and uvicorn;
# everything else is the Python standard library.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user; the service only needs its working directory.
RUN useradd --create-home --uid 10001 sumeravera \
    && chown -R sumeravera:sumeravera /app
USER sumeravera

ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/')"

CMD ["uvicorn", "sumeravera_core:app", "--host", "0.0.0.0", "--port", "8000"]
