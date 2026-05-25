# ---- Stage 1: builder ----
# Compiles Python wheels that need a C toolchain (psycopg2, bcrypt, asyncpg).
# These deps don't ship in the final image — only the resulting site-packages.
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install into a clean venv so the runtime stage can copy it whole — clearer
# than pip --user / --prefix tricks, and PATH expansion is just one line.
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

COPY requirements.txt ./
RUN pip install -r requirements.txt


# ---- Stage 2: runtime ----
# Slim image with only the runtime libs (libpq5 for psycopg2, curl for the
# optional Docker HEALTHCHECK). Cloud Run pulls this on cold start; smaller
# image = faster cold start.
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create a non-root user. Cloud Run sandboxes the container, but running as
# non-root is standard defense-in-depth — limits blast radius if anything in
# the Python stack ever pops a shell. UID 10001 is arbitrary but well above
# the system-user range, matching common conventions (e.g. distroless).
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --home /app app

# Copy the pre-built venv from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Copy app source. `.dockerignore` keeps caches/.env/.git out of the image.
COPY . .

RUN chmod +x /app/docker-entrypoint.sh \
    && chown -R app:app /app

USER app

EXPOSE 8000

# Docker HEALTHCHECK is for the Docker daemon — Cloud Run ignores it and uses
# its own readiness probe via the configured port. Kept for local / CI use.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8000}/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# Shell form so $PORT expands. Cloud Run injects PORT (default 8080); falls
# back to 8000 locally under docker-compose where PORT is unset.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
