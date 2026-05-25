#!/usr/bin/env bash
set -euo pipefail

# Wait briefly for Postgres to accept connections, then run migrations.
# The compose file gates startup on `service_healthy`, but in non-compose
# deployments this loop covers the small race when SYNC_DATABASE_URL points
# at a freshly-started instance.
python - <<'PY'
import os
import socket
import time
from urllib.parse import urlparse

raw = os.environ.get("SYNC_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
if not raw:
    raise SystemExit(0)

parsed = urlparse(raw.replace("postgresql+asyncpg", "postgresql"))
host = parsed.hostname or "localhost"
port = parsed.port or 5432

deadline = time.time() + 30
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit(f"Database at {host}:{port} did not become reachable in time.")
PY

alembic upgrade head

exec "$@"
