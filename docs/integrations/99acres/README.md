# 99acres integration — internal design

**Status:** design agreed, build not started. Blocked on 99acres' answers to
`99acres-information-request.md`.

| Document | Audience |
|---|---|
| `flexcrm-lead-api.md` | **External** — our endpoint contract, send to 99acres |
| `99acres-information-request.md` | **External** — what we need from them |
| `README.md` (this file) | **Internal** — architecture and build plan |

---

## Confirmed facts

- **Direction:** 99acres pushes to us. They asked for *our* API details, which settles it.
- **Account model:** every FlexCRM customer holds their **own** 99acres account. There is no
  master partner account, so this is per-tenant credentials — unlike Meta, where one platform app
  serves every tenant via OAuth.
- **Their docs:** none yet. This design deliberately avoids assuming anything about their API.

---

## What we reuse

The lead-ingest path is already provider-agnostic; this is mostly assembly.

- `LeadIngestService.ingest_lead(*, organization_id, actor_id, industry, source_provider,
  external_id, fields)` — `app/services/lead_ingest.py`. Handles idempotency, a SAVEPOINT with
  5-retry on `lead_number` collision, per-column length clamping, the triage-pool default, and the
  realtime broadcast.
- The DB idempotency anchor: partial-unique `(source_provider, external_id)` on `leads`
  (`app/models/lead.py`), already provider-neutral and scoped **per tenant schema**.
- The Fernet secret vault (`app/core/crypto.py`).
- `get_or_create_integration_user` — per-org, not per-provider, so 99acres reuses the same
  `integration+{org}@flexcrm.local` service account as Meta.
- The public-routing-table pattern (`app/models/meta_page_route.py`).

`"99acres"` is already a canonical lead source (`app/core/lead_normalize.py`), and
`source_provider` / `source` are plain `String` columns — **no enum migration is required**.

---

## The one thing we must not copy from Meta

Meta's webhook acknowledges `200` unconditionally and swallows processing errors. That is only
safe because `meta_lead_sync` polls and can re-fetch any lead by id — a permanent backstop.

**99acres is push-only. There is no poll, no re-fetch, no backstop.** Copying "always ACK 200"
verbatim would mean any bug or deploy blip silently destroys paid-for leads.

**Design: persist first, process second.** The endpoint writes the raw body to
`lead_source_deliveries` in its own transaction, returns `200`, then maps and ingests. A reconcile
cron drains anything left unprocessed. This keeps the friendly ACK contract *and* makes every
delivery replayable.

Question 5 in the information request asks whether they have *any* pull/export API — even a daily
one would restore a genuine backstop and is worth pushing for.

---

## Multi-tenant architecture

### Why routing must happen in `public`

An inbound webhook carries no JWT and arrives before we know which tenant it belongs to. Tenant
resolution therefore has to hit a **public** table before any tenant schema is touched — the same
reason `MetaPageRoute` lives in `public` while `MetaConnection` lives in `tenant`.

### Tables

**PUBLIC — `lead_source_routes`.** Generalised from `meta_page_routes` so MagicBricks and
Housing.com slot in later without another migration. Contains **no secrets and no PII**.

| Column | Purpose |
|---|---|
| `provider` | `"99acres"` |
| `connection_ref` | opaque non-secret id used in the callback URL — `UNIQUE` |
| `external_account_id` | their account/client id (nullable until known) |
| `organization_id` | FK → `organizations.id`, `ON DELETE CASCADE` |
| `schema_name` | denormalised so routing is a single lookup |
| `is_active` | soft disable |
| — | `UNIQUE(provider, external_account_id)` → **one 99acres account ↔ exactly one tenant** |

**TENANT — `lead_source_connections`.** `provider`, account id, `secret_encrypted` (Fernet),
`default_industry` as a plain `String(20)` (**not** the enum — see the cross-schema enum trap in
`migrations_tenant/README.md`), `field_map` JSON, `integration_user_id`, `status`/`status_detail`,
`is_active`, soft-delete.

**TENANT — `lead_source_deliveries`.** Raw body, header subset, `received_at`, `processed_at`,
`status`, `error`, `external_id`. The replay / dead-letter log.

> **Why deliveries are tenant-scoped, not public:** payloads carry lead PII. Storing them in
> `public` would break the isolation model that keeps the routing table free of secrets and
> personal data. Order of operations is therefore: resolve route (public, cheap) →
> `set_tenant_schema` → persist → ACK → process.
>
> An **unrouted** delivery has no tenant to belong to, so we log structured metadata and increment
> a counter, deliberately persisting **no PII** for traffic we cannot attribute.

### Per-tenant onboarding

1. Platform admin enables the `portal_99acres` module for the org.
2. Tenant opens **Settings → Integrations → 99acres** → *Create connection*.
3. We mint a `connection_ref` and a high-entropy secret, shown **once**. The secret is stored
   Fernet-encrypted; the route row is written in `public`.
4. The tenant gives the URL + secret to their 99acres account manager.
5. 99acres posts → we resolve `connection_ref` → `set_tenant_schema` → persist → ingest into
   **that org's schema only**.

### What this gives us at 10 tenants

10 route rows, 10 distinct secrets, and leads landing in 10 separate Postgres schemas. A tenant
cannot see another's leads because those rows are not in their schema at all — isolation is
physical, not a `WHERE` clause.

Claiming an already-connected 99acres account fails twice over: a friendly `ValidationError` (422)
in the normal case, and `UNIQUE(provider, external_account_id)` as the race-proof backstop. Same
belt-and-braces as `MetaConnectionService._register_page_route`.

### Routing key — designed to survive either answer

- **Per-account callback URL** (our preference): route on `connection_ref` in the path. No
  dependency on payload contents.
- **One shared URL for all their clients:** route on `account_id` in the payload; the tenant
  registers their 99acres account id at connect time.

The route table carries both keys so either answer to question 2 works without a redesign.

---

## Build phases

Mirrors how the Meta integration shipped (~10 small, independently reviewable commits).

| Phase | Work |
|---|---|
| **P0** | Generalise the seams: `meta_page_routes` → `lead_source_routes` keyed on `(provider, external_account_id)`; add `"99acres": "99acres Lead"` to `_PROVIDER_FALLBACK_NAME`; alias `META_ENC_KEYS` → `INTEGRATION_ENC_KEYS`. No behaviour change; the Meta path must stay green. |
| **P1** | Data layer: public migration (`down_revision = "20260817_0111"`) + tenant migration (`down_revision = "20260814_t030"`), models, registration in `app/models/__init__.py`. |
| **P2** | Inbound endpoint: auth verification, persist-then-ACK, tenant resolution, per-delivery error isolation, module gate, rate-limit exemption. |
| **P3** | Mapper + ingest. Emit the literal `"99acres"` as `source` so it matches `SOURCE_LABELS` and the existing list filter — the Meta mapper does the same rather than calling `normalize_source`. Unmapped fields append to `notes` so nothing is lost. |
| **P4** | Reconcile cron draining unprocessed deliveries. Rides the **existing** `30 3` trigger — a third cron wakes Neon more often, which is why the old keep-alive was removed. |
| **P5** | Tenant UI. `IntegrationsPage.tsx` is currently a single Meta-specific component; add a 99acres card and lift the shared status chrome. |
| **P6** | Module flag `portal_99acres` — prefixed to avoid a leading-digit key and to namespace future portals. |

### Traps to avoid

- **The rate limiter will throttle 99acres.** It keys on `client_host + path` at 120/min and
  exempts only `/health`, `/docs`, `/openapi.json`, `/redoc` (`app/middleware/rate_limit.py`).
  Behind Cloud Run every caller shares one client IP because uvicorn runs without
  `--proxy-headers`. The webhook prefix needs an exemption. *(The Meta webhook has the same latent
  exposure today.)*
- **`docs/adding-a-module.md` is incomplete.** It omits three files a new module must touch:
  `OrgContext.tsx` `ALL_OFF`, the runtime `MODULE_KEYS` array in `types/crm.ts`, and the build-flag
  route gate in `App.tsx` — miss that last one and the page is unroutable. Fix the doc in P6.
- **`PATCH /admin/organizations/{id}/modules` silently drops unknown keys**
  (`app/api/v1/endpoints/admin.py`), so a missing `MODULE_KEYS` entry fails with no error at all.
- `LeadRead` does not expose `source_provider` / `external_id`, so lead provenance is invisible in
  the UI until those are added.

---

## Verification

There are currently **zero tests for the Meta integration**, so 99acres ships with its own.

1. `cd backend && pytest` — full suite green (the Meta path is unchanged by P0).
2. New tests: two orgs claiming the same 99acres account → the second gets 422/409; a delivery for
   org A never appears in org B; redelivery of the same `external_id` is a no-op; a mapper failure
   leaves a replayable `lead_source_deliveries` row rather than losing the lead. Follow the
   parameterised per-org isolation shape in `tests/test_jobs_tenancy.py`.
3. Real Postgres, two provisioned tenant schemas: POST a sample payload to each tenant's URL and
   confirm the lead lands in the right schema, unassigned, with `source_provider="99acres"` and
   `source="99acres"`.
4. Wrong or absent secret → 403 with **no** delivery row. Malformed body with a valid secret → 422
   with the delivery row retained.
5. Burst 500 payloads in a minute → all accepted, proving the rate-limit exemption.
6. `npm run build` (runs `tsc --noEmit`) — the module-key union change touches several files and TS
   enforces exhaustiveness on `MODULE_LABELS`.
