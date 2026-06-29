# Python 3.12-slim: stable, prebuilt wheels for pydantic-core/uvicorn/hyperion.
# Avoids the 3.14 source-build pain noted in the project README.
FROM python:3.12-slim

# Unbuffered stdout/stderr so logs appear immediately in `docker compose logs`.
# Dontwritebytecode keeps the image clean of .pyc cruft.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Layer cache: install deps before copying app code.
# requirements.txt changes rarely; app/ changes every deploy.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code, templates, and static assets.
# .dockerignore ensures magic.db, .venv, __pycache__, .git are excluded
# from the build context even if COPY globs widen later.
COPY app/ ./app/
COPY templates/ ./templates/
COPY public/ ./public/

# Run uvicorn as a non-root user. Container root is avoided per best practice.
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Production uvicorn invocation:
#   --host 0.0.0.0          bind to all interfaces (container requirement)
#   --port 8000             match EXPOSE and compose config
#   --workers 1             REQUIRED: the app uses a module-level singleton
#                           aiosqlite connection + in-memory recommendation
#                           cache. Multiple workers would each open their own
#                           SQLite connection and diverge. Single-user load
#                           does not need >1 worker.
#   --proxy-headers         trust X-Forwarded-* from Caddy so request.client
#                           and any redirect logic see the real client IP.
#   --forwarded-allow-ips=* accept forwarded headers from the Caddy container
#                           on the compose bridge network (safe here: only
#                           Caddy can reach port 8000 — it is not published).
#   (no --reload)           reload is a dev feature; omitted in prod.
CMD ["uvicorn", "app.application:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--proxy-headers", \
     "--forwarded-allow-ips=*"]
