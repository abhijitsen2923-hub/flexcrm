# FlexCRM — Project Handoff / MEMORY (as of 2026-08-21)

> Complete record of the FlexCRM application — architecture, every module, deployment, current status,
> and the roadmap — written so you can step away (or hand off) and resume with zero context loss.
> The Meta Lead Ads integration is the most recent work and the only thing currently blocked; it has
> its own detailed section (§7).

---

## 1. What FlexCRM is

A **multi-tenant (schema-per-tenant) SaaS CRM**, primarily configured for **real-estate**, but the core
supports **education** and **travel** verticals too (they differ by pipeline config + CSV columns, not
separate code). A tenant = one `Organization` = one Postgres schema.

**Stack**

| Layer | Tech |
|---|---|
| Backend | FastAPI (async) · SQLAlchemy 2.0 (asyncpg) · Alembic · Pydantic v2 · JWT (python-jose) · bcrypt · Redis cache · WeasyPrint (PDF) |
| DB | Neon serverless Postgres (schema-per-tenant) |
| Frontend | React 18 · Vite 6 · TypeScript 5 · react-router-dom 6 · axios · recharts · lucide-react · Context (no Redux) |
| Hosting | Backend → Cloud Run (`flexcrm-backend`, asia-south1, project `flex-crm-497410`). Frontend → Cloudflare Worker (`https://flexcrm.abhijitsen2923.workers.dev`) serving the Vite SPA + running the cron scheduler |

---

## 2. Architecture & cross-cutting patterns

**Multi-tenancy (the backbone).** `app/core/tenancy.py`. Tenant models declare `{"schema":"tenant"}`;
SQLAlchemy `schema_translate_map` rewrites `"tenant"` → the real schema per request. Public/shared tables
(organizations, users, refresh_tokens, pipeline_stages, meta_page_routes) live in `public` and are never
translated. Two SQLAlchemy event listeners re-apply the map to every statement/new transaction so routing
survives commits across the pooled connections. `bypass()` = cross-org lookups (auth); `set_scope`/
`current_org` store org_id in `session.info`. Platform admins skip tenant routing entirely.

**Auth & permissions.** `app/core/security.py` (JWT access 15min + rotating refresh 7d, bcrypt),
`app/core/permissions.py` (~24 `DOMAIN_VERB` `PermissionCode`s + per-role defaults + coarse→fine aliases;
`CustomRole` templates; additive `UserPermissionGrant`s). Gates in `app/api/deps.py`
(`require_permissions`, `require_platform_admin`, `require_broker`). Roles are vertical-scoped
(`ROLE_INDUSTRIES`); front-line reps (`ASSIGNED_ONLY_LEAD_ROLES`) only see their own leads; RE stage moves
gated by `ROLE_STAGE_ACCESS`.

**Request pipeline.** `app/main.py` `create_app()` → CORS + `RateLimitMiddleware` (Redis, per-IP+path,
fail-open) + `RequestContextMiddleware` (X-Request-ID + timing). Lifespan: configure DB, connect cache,
`ensure_platform_admin`, best-effort `upgrade_all_tenant_schemas()`.

**Layering.** endpoint (permission-gated) → **Service** (`ServiceBase`: holds session, `commit()` maps
`IntegrityError`→`ConflictError`, `invalidate_reporting_cache()`) → **Repository** (`BaseRepository`:
soft-delete filter, filters/search/sort/pagination, CRUD) → **Model** (UUID PK, audit + soft-delete
mixins; tenant mixins use cross-schema FKs to `public.users`). Pydantic schemas per domain
(Create/Update/Read/Filter). Uniform error envelope `{error:{code,detail,extra},request_id,path}`
(`app/core/exceptions.py`). Redis cache (`app/core/cache.py`, in-memory fallback dev only).

**Realtime.** `app/services/realtime.py` (`RealtimeManager`) — in-process, **org-scoped** fan-out via a
`_broadcast_org` contextvar, per-org ring buffer for reconnect replay. WS endpoint `/ws/updates`
(`websocket.py`). Events: `lead.stage_changed`, `customer.promoted`, `unit.status_changed`,
`notification.created`, `lead.created`. ⚠️ In-process only — multi-worker needs Redis pub/sub (known
caveat).

---

## 3. Backend modules

### Core CRM

| Module | Endpoint | Service(s) | Notes |
|---|---|---|---|
| **Leads** (centerpiece) | `leads.py` | `leads.py`, `stage_transitions.py`, `lead_import.py`, `lead_ingest.py`, `lead_documents.py` | list (own-only for reps), duplicates, campaigns, bulk-reassign, bulk-transition, call logs, CSV import + template, documents. **`StageTransitionService` is the ONLY path to change `stage_code`** — enforces mandatory ≥10-char comment, role/backward gates, auto-promotes lead→customer + materializes SalesOrder/Invoice/commission/brokerage on `sold`, reverses on reopen |
| Customers + lifecycle | `customers.py`, `customer_lifecycle.py` | `customers.py`, `customer_promotion.py`, `customer_lifecycle.py` | promote-from-lead (idempotent), delivery/renewals/referrals, `evaluate_health` + `recompute_ltv` |
| Deals | `deals.py` | `deals.py` | stage/status/amount, FK→customers |
| Tasks | `tasks.py` | `tasks.py` | priority/status, assignee notify |
| Activities | `activities.py` | `activities.py` | typed activity log |
| Pipeline stages | `pipeline_stages.py` | — | per-vertical ordered stage catalog (public/shared); seed `database/pipeline_seed.py` |
| Users / Orgs | `users.py`, `organizations.py` | `users.py` | users in public schema, org-scoped; `get_or_create_integration_user` (Meta ingest) |
| Notifications | (no REST) | `notifications.py` | created in-code, pushed via realtime |
| Auth / permissions / custom roles / platform admin | `auth.py`, `permissions.py`, `custom_roles.py`, `admin.py` | `auth.py` | see §2; admin = cross-org module toggles, suspend/archive/purge (drops schema), tenant-schema upgrade |

### Verticals
- **Real Estate** — `app/real_estate/` (richest module). Inventory (Projects → Towers → Units, batch unit
  gen, media), **Site visits**, **Bookings** (4-step wizard, double-booking guard, payment plans,
  collections ledger, demand-note invoices `INV-RE`, KYC docs, cancel/refund/register), **Registration**
  + **Possession** trackers. Unit lifecycle: available→hold→booked→registered→sold. PDF docs (allotment
  letter, booking form, receipts) via WeasyPrint. Models: `Project, ProjectMedia, Tower, Unit, SiteVisit,
  Booking, BookingKycDoc, PaymentSchedule, PaymentReceipt, BookingRefund, BookingInvoice`.
- **Finance** — `app/finance/`. Triggered off `sold`: SalesOrder + auto-Invoice + CommissionLedger.
  Payments flip invoice→paid & commission accrued→payable; refunds reverse commission + partner brokerage.
  Assist splits (prior owners default 20%). Monthly reports. Models: `SalesOrder, SalesOrderAssist,
  Invoice, Payment, CommissionLedger, Refund`.
- **HR** — `app/hr/`. Sales scorecards: weighted composite (revenue/collections/conversion/velocity/
  activity/retention), graded A+…D, computed nightly. Models: `EmployeeProfile, PerformanceSnapshot`.

### Portals & partners
- **Customer portal** — `app/customer_portal/` (`/customer`, role `customer`): payment status, document
  downloads, service requests, referral submit (creates a lead). Frontend is a **PWA**.
- **Channel Partners** (staff-facing) — `channel_partners.py` + `services/channel_partners.py`: broker
  roster, PAN/bank, brokerage accrual/reversal, payouts.
- **Partner portal** (broker self-service) — `partner_portal.py` (`/partner`, `require_broker`):
  dashboard, submit referral lead, lead tracker, commissions.

### Analytics / exports / import
- Analytics (`/analytics`) + Dashboard (`/dashboard`) — cached. Exports (`/exports`) — CSV for
  leads/customers/sales-orders/inventory/bookings (vertical-aware columns via `core/lead_csv`).
- **CSV lead import** — `POST /leads/import` + `services/lead_import.py`: vertical-aware column mapping,
  duplicate detection, normalization, reuses LeadService+StageTransitionService (a `stage=sold` row fires
  full auto-promotion). Partial success with per-row errors. (Recent work added Campaign + Assignee columns
  and dynamic campaign filtering; email is optional, phone required.)

### Integrations — Meta → see §7.

### Jobs & crons — `app/jobs/*` (each iterates all orgs, per-org schema switch + commit, isolates failures):
`followup_reminders` (daily), `registration_reminders` (daily), `meta_lead_sync` (poll), `meta_token_refresh`
(daily), `scorecard_compute` (nightly), `customer_health` (nightly), `archive` (retention purge).
All seven are exposed as HTTP crons in `cron.py` (`X-Cron-Key` == `settings.cron_secret`) and wired into the
Worker's `scheduled` handler.

> ⚠️ **Corrected 2026-08-22.** The "each iterates all orgs" claim above was NOT true for three of them.
> `archive` had no org loop at all, and `customer_health` + `scorecard_compute` called only `set_scope()` —
> a documented no-op stub — without `set_tenant_schema()`, so every per-tenant query targeted the literal
> `tenant` schema. All three were CLI-only, so nothing ever invoked them and nothing failed loudly: retention
> purging, customer-health/churn evaluation and HR scorecards had never run in production. `scorecard_compute`
> additionally queried the legacy `{sales, manager, admin}` roles (unassignable since migration `0010`) via
> `list_active_sales_users`, which also had **no `organization_id` filter** — `users` is public and shared, so
> it returned every tenant's users. Fixed: all three now follow the `followup_reminders` pattern, the role set
> moved to `SCORECARD_ROLES` in `core/permissions.py`, and `clear_tenant_schema()` was added to `core/tenancy.py`
> so archival's public `users` pass runs unrouted after the org loop.

---

## 4. Frontend

Entry `src/main.tsx` → `src/App.tsx`. Providers: `ErrorBoundary → BrowserRouter → Toast → Auth → Org →
Realtime → Pipeline`. **Three surfaces**, split by role in `ProtectedRoute`:
- **Staff console** (`/`, `AppLayout` sidebar): Dashboard, Leads, Customers, Deals, Tasks, Activities,
  Analytics, Finance, HR, Projects, Inventory, Site-visits, Bookings, Registration/Possession trackers,
  Channel-partners, Integrations, Users (users+roles tabs), Admin (platform admin). Most routes are
  lazy-loaded + **feature-flag + per-org-module gated**.
- **Customer portal** (`/customer`, PWA, role `customer`): payments, documents, service, refer.
- **Partner portal** (`/partner`, role `broker`): dashboard, submit, leads, commissions.

**Services** `src/services/*` — one `*Service` per domain over `http.ts` (axios: Bearer inject,
transient-retry for 502/503/504 + network sized to survive Cloud Run cold start, single-flight 401→refresh).
**Contexts** `src/context/*` (Auth, Org+modules, Pipeline) + `src/realtime/RealtimeContext.tsx` (WS).
**Feature flags** `src/config/features.ts` — module shows only when **build flag `VITE_FEATURE_*` AND
per-org toggle** both agree (`mergeModules`). `meta_facebook`+`meta_instagram` share build flag
`VITE_FEATURE_META_LEADS_ENABLED`. **Components** `src/components/ui/*` (Badge, Button, Card, DataTable,
Modal, FormField, Toast…), `layout/*` (AppLayout, Sidebar, Topbar, MobileBottomNav), `routing/*` guards.

---

## 5. Data layer & migrations

- **Two Declarative bases** (`app/database/base.py`): `Base` (public) + `TenantBase`
  (`MetaData(schema="tenant")`). Cross-schema FKs resolved via public stub tables.
- **Enums** single-source in `app/database/enums.py` (all StrEnum).
- **TWO Alembic chains** (key deployment nuance):
  - **Public** — `migrations/` + `alembic.ini` (`target_metadata=Base.metadata`). Head `20260817_0111`
    (…meta_page_routes 0110, provider_user_id 0111). **Run at container boot** by `docker-entrypoint.sh`.
  - **Tenant** — `migrations_tenant/` + `alembic_tenant.ini` (`target_metadata=TenantBase.metadata`). Head
    `20260805_t030` (meta_connections oauth cols). `env.py` supports single-schema (provisioning) and batch
    (all schemas) modes via `TARGET_SCHEMA`. **Applied in-app** by `upgrade_all_tenant_schemas()` at
    lifespan startup + at provision time. Both env files import all vertical model packages.
- **Provisioning** — `app/services/tenant_provisioner.py`: validate schema name → `CREATE SCHEMA` (own
  txn) → run tenant chain in a thread → verify ≥20 tables.

---

## 6. Deployment & ops

- **Backend** `backend/Dockerfile` (2-stage; runtime includes WeasyPrint native libs). `docker-entrypoint.sh`
  waits for Postgres → `alembic upgrade head` (public) → `uvicorn app.main:app`. Cloud Run injects `$PORT`;
  `/health` + `/health/db` (Neon keep-warm). Config via env: `SYNC_DATABASE_URL`, JWT secrets,
  `REDIS_URL`, `CORS_ORIGINS`, `CRON_SECRET`, `META_ENC_KEYS`, `META_APP_*`, `APP_BASE_URL`, platform-admin
  bootstrap, SMTP/Resend, S3.
- **Frontend** `frontend/wrangler.jsonc` + `worker/index.js` — Worker serves `./dist` (SPA fallback) and
  runs the cron `scheduled` handler → POSTs backend `/cron/*` with `X-Cron-Key`. Crons (UTC): `30 3`
  (09:00 IST) = poll + reminders + follow-ups + token-refresh; `30 15` (21:00 IST) = poll only. Build =
  `tsc --noEmit && vite build`. **Build-time vars** (must be set in Cloudflare, NOT committed):
  `VITE_API_BASE_URL`, `VITE_FEATURE_META_LEADS_ENABLED`, and the other `VITE_FEATURE_*`.
- **Handoff flags:** no test/lint/CI in frontend; `VITE_API_BASE_URL` + `VITE_FEATURE_META_LEADS_ENABLED`
  live only in Cloudflare build env (a fresh deploy that forgets them points at localhost + hides
  Integrations). Realtime is single-worker (needs Redis for scale-out).

---

## 7. Meta (Facebook/Instagram) Lead Ads integration — DETAILED

**Goal:** a tenant's Lead Ads form submissions become live CRM leads automatically (no CSV). Two connect
methods, same pipeline (only token acquisition differs): **BYO** (paste a System-User token; poll-only) and
**OAuth "Connect Facebook"** (one-click login; real-time webhook + auto token refresh).

**Built & shipped** (all on `main`):

| Commit | What |
|---|---|
| `26db48b` | Phase 1 — OAuth connect foundation (coexists with BYO) |
| `4131f23` | Phase 2 — real-time leadgen webhook (verify + HMAC signature + route + ingest; subscribe-on-connect) |
| `2de2f97` | Phase 3 — token-refresh cron + deauthorize + data-deletion callbacks |
| `f85a85d` | Phase 4 — frontend "Connect Facebook" button + Page-picker (BYO demoted to "Advanced") |
| `7141c76` | Wire Meta crons into the Worker (poll 09:00 & 21:00 IST; token-refresh 09:00) |
| `1b05d3f` | OAuth supports Facebook Login for Business `config_id`; drop `business_management` scope |

Each phase passed an adversarial multi-agent review before commit (all confirmed findings fixed).

**Architecture:** one platform Meta app serves all tenants. Outbound OAuth bound by HMAC-signed `state`
(org_id); inbound webhooks routed by `page_id` via the PUBLIC `MetaPageRoute` registry (unique page_id →
org+schema; enforces one-Page-one-tenant). Tokens Fernet-encrypted (`core/crypto`, `META_ENC_KEYS`), never
returned. Ingest via provider-agnostic `LeadIngestService` (idempotent on `(source_provider, external_id)`).
Webhook = real-time (OAuth); poll (`meta_lead_sync`) = permanent backstop + only path for BYO. Files:
`services/meta_{oauth,connection,webhook,graph,sync,mapper}.py`, `jobs/meta_{lead_sync,token_refresh}.py`,
`models/meta_{connection,page_route}.py`, endpoints `integrations.py` + `webhooks.py`.

**⚠️ THE ONE BLOCKER — Meta App Review (read this first when resuming).**
Reading Lead Ads leads requires the `leads_retrieval` permission, which Meta gates behind **App Review +
Business Verification (Tech Provider)**. **Confirmed empirically (2026-08-21) that there is NO dev-mode /
Standard-Access / BYO shortcut:** `leads_retrieval` is absent from every use case (consumer Facebook Login,
Marketing API, Manage-everything-on-your-Page) and is NOT offered even for a System-User (BYO) token on the
org's own Page ("No matching results"). The other perms DO come at Standard/"Ready for testing"
(`pages_show_list`, `pages_read_engagement`, `pages_manage_metadata`, `business_management`, `ads_management`).
So BOTH connect methods are blocked on the same gate. The FlexCRM code is complete and inert-ready; only
Meta's approval is missing.

**Meta dashboard state (Vista Ventures):** business portfolio `971519592533664`; Page **Vista Ventures
Realtor - VVR**, Page ID **`1176497002210453`**; system user **CRM Integration** (id 61592840412995, has
Full access to the Page); usable app **VistaVentures CRM** (id `1035575606129011`, Marketing API + Facebook
Login for Business); dead-end app **FlexCrm** (id 1025986590068844, consumer login — ignore); webhook verify
token = `flexcrm`. Backend env set + verified from outside (webhook handshake → 200; callback redirect →
correct https frontend URL).

**Meta callback/webhook URLs** (backend `https://flexcrm-backend-539170436218.asia-south1.run.app`):
OAuth redirect `…/api/v1/integrations/meta/oauth/callback` · webhook `…/api/v1/webhooks/meta` · deauthorize
`…/api/v1/webhooks/meta/deauthorize` · data-deletion `…/api/v1/webhooks/meta/data-deletion`.

---

## 8. Current status & roadmap

**Status:** Application is live and feature-complete across all modules above. The Meta integration is
built + deployed + verified, **blocked only on Meta App Review** for `leads_retrieval`.

**Meta roadmap (to unblock real leads):**
1. **App Review pack** (long-pole): public Privacy Policy + Data-Deletion pages; `leads_retrieval`
   use-case justification; reviewer screencast script. *(Not started — paused here.)*
2. **Business Verification** + **Become a Tech Provider** (Meta dashboard; identity/business docs; free).
3. **Submit App Review** for `leads_retrieval` → flip app to **Live**.
4. **After approval:** OAuth → create a Facebook-Login-for-Business configuration → set
   `META_LOGIN_CONFIG_ID` on Cloud Run (code already supports it). BYO → generate System-User token (now
   with `leads_retrieval`) + grant Lead Access + accept Lead Ads ToS → paste token + Page ID
   `1176497002210453` into FlexCRM → Advanced → Test → Connect.
5. **Optional anytime:** an admin-only "inject test lead" via `LeadIngestService` to demo the full flow
   (triage → notify → realtime) before Meta approves. *(Not built.)*

**Backend test suite (repaired 2026-08-22).** Previously described here as merely "stale". It was in fact
structurally broken and had not run since the multi-tenancy migration (`20260522_0006`): `conftest.py` only
ever called `Base.metadata.create_all`, and 36 of 41 models are `TenantBase` — whose separate
`MetaData(schema="tenant")` was never passed to `create_all` anywhere in the repo — so no tenant table existed
in the test DB. The `auth_headers` fixture also asserted `register → 201` while `register` calls
`provision_tenant()`, which issues Postgres-only DDL (`to_regclass` / `CREATE SCHEMA`) against SQLite.
Baseline was **18 passed / 12 failed / 44 errors**; now **77 passed / 4 skipped**.

The harness **collapses `tenant` and `public` into one schema** (SQLite has no `CREATE SCHEMA`, and
cross-database FKs are unsupported while every tenant table has FKs into `public`). So it covers business
logic, *not* tenant isolation — 4 isolation tests are skipped with that reason and need real Postgres. See the
header comment in `backend/tests/conftest.py`. `backend/pytest.ini` was added so the documented bare `pytest`
command works (previously only `python -m pytest` could import `app`).

**Two production bugs the repaired suite immediately exposed:**
- `Task` had no `assigned_to` relationship while `TaskRepository.default_options` did
  `selectinload(Task.assigned_to)` → `AttributeError` on **every** task list/get/create/update. The whole
  Tasks module was 500ing. Same bug class as the one already fixed for `StageTransition.performed_by`.
- `LeadImportService` held `PipelineStage` **ORM objects** in its stage lookup across the row loop. A failing
  row calls `session.rollback()`, which expires them, so the *next* row raised `MissingGreenlet` — meaning any
  CSV import with a mid-file failure aborted every subsequent row, contradicting the documented
  partial-success behaviour. Now snapshotted to a detached `StageRef`.

**Other known deferred items:** realtime multi-worker (needs Redis pub/sub); WhatsApp conversational inbox
(scoped, deferred). **Open findings not yet fixed** (surfaced during the 2026-08-22 review, listed most severe
first): cross-tenant lead assignment (`bulk_reassign` does a bare `UPDATE` with no reference check, and
`UserRepository` has no org filter, so a lead can be assigned to another org's user); 429 responses carry no
CORS headers because `CORSMiddleware` is added first and so runs innermost; rate limiting is effectively global
behind Cloud Run since uvicorn starts without `--proxy-headers`; `EXPOSE_ERROR_DETAIL` and `DOCS_ENABLED`
default `True` and are not covered by `_reject_insecure_production`; legacy `UserRole.admin` still grants all 24
permissions; WebSocket auth ignores user status and org lifecycle.

---

## 9. Key file index
- App factory/lifespan `app/main.py`; routes `app/api/v1/api.py`; deps/gates `app/api/deps.py`.
- Tenancy `app/core/{tenancy,config,security,permissions,exceptions,cache,crypto}.py`.
- Core services `app/services/{leads,stage_transitions,customers,customer_promotion,deals,tasks,
  notifications,realtime,users,auth}.py`; base `services/base.py`, repos `app/repositories/*`.
- Verticals `app/real_estate/*`, `app/finance/*`, `app/hr/*`, `app/customer_portal/*`; partners
  `endpoints/{channel_partners,partner_portal}.py` + `services/channel_partners.py`.
- Import/export `services/lead_import.py`, `endpoints/{exports,leads}.py`, `core/lead_csv.py`.
- Meta `endpoints/{integrations,webhooks}.py`, `services/meta_*.py`, `jobs/meta_*.py`, `models/meta_*.py`.
- Data `app/models/*`, `app/database/{base,enums,session,pipeline_seed}.py`; migrations `migrations/`
  (public) + `migrations_tenant/` (tenant); provisioning `services/tenant_provisioner.py`.
- Deploy `backend/Dockerfile`, `backend/docker-entrypoint.sh`; frontend `wrangler.jsonc`,
  `worker/index.js`; frontend app `src/{App.tsx,pages,services,context,components,config/features.ts}`.
