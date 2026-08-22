# FlexCRM

A full-stack CRM (customers, leads, deals, tasks, activities, dashboards, analytics) with role-based access, JWT auth, real-time WebSocket updates, and Redis-backed caching/rate-limiting.

- **Backend** — FastAPI (Python 3.10+) + SQLAlchemy 2.0 async + PostgreSQL + Alembic
- **Frontend** — React 18 + TypeScript + Vite + axios + recharts
- **Cache** — Redis (in-memory fallback for single-worker dev)

> Authoritative project context — architecture, every module, deployment, current status and roadmap — lives in [MEMORY.md](MEMORY.md). Read it before changing architecture or adding dependencies.

---

## Repository layout

```
.
├── backend/         # FastAPI service
│   ├── app/
│   ├── migrations/  # Alembic
│   ├── tests/       # pytest
│   ├── requirements.txt
│   └── alembic.ini
├── frontend/        # React + Vite SPA
│   └── src/
├── .env.example     # backend env template
├── docker-compose.yml
└── README.md
```

---

## Quickstart — Docker (recommended)

Prereqs: Docker Desktop (or Docker Engine + Compose v2).

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
docker compose up --build
```

The stack brings up:

| Service  | URL                                                    | Notes                                                |
| -------- | ------------------------------------------------------ | ---------------------------------------------------- |
| backend  | http://localhost:8000                                  | FastAPI + auto-migrated schema                       |
| postgres | localhost:5433 (`crm`/`postgres`/`postgres`)           | Host port configurable via `POSTGRES_HOST_PORT`      |
| redis    | localhost:6380                                         | Host port configurable via `REDIS_HOST_PORT`         |
| docs     | http://localhost:8000/docs                             | Swagger UI                                           |

> Host ports default to **5433** and **6380** to avoid colliding with locally-installed Postgres/Redis on 5432 / 6379. Override via `POSTGRES_HOST_PORT` / `REDIS_HOST_PORT` in `.env` if the standard ports are free for you.

The frontend is **not** containerized — run it locally (see below).

To run Alembic migrations manually (e.g. after editing a model):

```bash
docker compose exec backend alembic upgrade head
```

To tear down (preserving volumes):

```bash
docker compose down
```

---

## Quickstart — Local

### Backend

Prereqs: Python 3.10+, PostgreSQL 13+, Redis 6+ (optional but recommended).

```bash
cd backend
python -m venv .venv
. .venv/bin/activate           # on Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Configure env (one level above `backend/`)
cp ../.env.example ../.env
# Edit ../.env — at minimum set DATABASE_URL, SYNC_DATABASE_URL, JWT_*

# Create schema
alembic upgrade head

# Run
uvicorn app.main:app --reload --port 8000
```

### Frontend

Prereqs: Node.js 18+.

```bash
cd frontend
npm install
cp .env.example .env
npm run dev                    # http://localhost:5173
```

> **Feature flags.** Every module is gated by **both** a build flag (`VITE_FEATURE_*` in
> `frontend/.env.production`) **and** a per-org toggle granted in Platform Admin — a module
> shows only when both agree. See [docs/adding-a-module.md](docs/adding-a-module.md).
> `VITE_API_BASE_URL` is **not** committed; it comes from the Cloudflare build environment,
> and a deploy that omits it silently points the app at `http://localhost:8000/api/v1`.

---

## Configuration

All backend env vars are documented in [.env.example](.env.example) and resolved in [backend/app/core/config.py](backend/app/core/config.py). Frontend vars live in [frontend/.env.example](frontend/.env.example).

**Required:** `DATABASE_URL`, `SYNC_DATABASE_URL`, `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`.

### Multi-worker / multi-replica deployment

The backend's rate limiter and cache use Redis when available, with a per-process in-memory fallback. **The in-memory fallback is correct only for a single Uvicorn worker.** For any deployment with `--workers > 1` or multiple replicas:

1. Provision Redis and set `REDIS_URL`.
2. Set `ENVIRONMENT=production` — this makes the app **fail to start** if Redis is unreachable, so misconfiguration can't silently degrade rate-limiting to per-worker.

For single-worker dev/test, the fallback remains a convenience.

---

## Testing

```bash
cd backend
pytest                         # runs the full test suite against an in-process sqlite db
```

The tests use the ASGI transport (no live server) and spin up an isolated sqlite database per test via [backend/tests/conftest.py](backend/tests/conftest.py).

> ⚠️ **The suite runs on a single collapsed schema.** Production is Postgres with
> schema-per-tenant, which SQLite cannot model — it has no `CREATE SCHEMA`, and cross-database
> foreign keys are unsupported while every tenant table has FKs into `public`. So the harness
> maps both `tenant` and `public` onto one schema and stubs tenant provisioning out.
> **These tests cover business logic, not tenant isolation** — a handful of isolation tests are
> skipped with that reason and need a real Postgres to be meaningful. See the header comment in
> `conftest.py` before adding a test that depends on cross-org invisibility.

---

## Architecture cheat sheet

```
Request
  → CORSMiddleware
  → RateLimitMiddleware       (per-IP, Redis-backed)
  → RequestContextMiddleware  (X-Request-ID, request log)
  → Endpoint (api/v1/endpoints/*.py)
      → Service (services/*.py)        ← business logic, transactions, cache invalidation
        → Repository (repositories/*.py) ← SQLAlchemy queries
          → Model (models/*.py)        ← SQLAlchemy ORM with audit/soft-delete mixins
  ← Pydantic schema (schemas/*.py)
```

See [MEMORY.md §2](MEMORY.md) for the full layered-architecture rules and what each layer is allowed to do.

---

## Useful endpoints

| Path                              | Purpose                              |
| --------------------------------- | ------------------------------------ |
| `GET /health`                     | Liveness probe                       |
| `GET /docs`                       | Swagger UI (when `DOCS_ENABLED=true`) |
| `POST /api/v1/auth/register`      | Sign up (first user becomes admin)   |
| `POST /api/v1/auth/login`         | Issue access + refresh tokens        |
| `POST /api/v1/auth/refresh`       | Rotate access token                  |
| `WS   /api/v1/ws/updates?token=…` | Real-time event stream               |

A full module + endpoint inventory is in [MEMORY.md §3](MEMORY.md).

---

## License

Internal / unspecified.
