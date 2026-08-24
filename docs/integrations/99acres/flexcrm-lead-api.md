# FlexCRM — Lead Ingestion API

**For:** 99acres integration team
**Status:** Proposed contract — v0.1
**Companion document:** `99acres-information-request.md` (the details we need from you)

> This document specifies the endpoint 99acres would call to deliver leads into FlexCRM.
> A few details are marked **[TBC]** because they depend on your answers in the companion
> document. Everything else is settled and will not change.

---

## 1. Overview

FlexCRM is a multi-tenant CRM. Each of our customers (a builder or brokerage) holds **their own
99acres account**, and each gets their **own dedicated endpoint URL and credential** from us.

You do not need to know anything about our internal tenant structure. From your side the model is
simply: *one 99acres account → one URL + one secret*, issued by us during onboarding.

```
99acres  ──POST new lead──►  FlexCRM endpoint (unique per account)
                             │
                             ├─ authenticate
                             ├─ store the raw payload durably
                             ├─ respond 200
                             └─ create the CRM lead (async)
```

---

## 2. Endpoint

```
POST {BASE_URL}/api/v1/webhooks/99acres/{connection_ref}
Content-Type: application/json; charset=utf-8
```

- `{BASE_URL}` — currently `https://flexcrm-backend-539170436218.asia-south1.run.app`.
  A branded custom domain may replace this before go-live; we will give you the final value in
  writing, and we will support both for a transition period.
- `{connection_ref}` — an opaque, **non-secret** identifier we issue per 99acres account. It only
  identifies which account is sending; it does not authenticate. Example:
  `c_7f3a91be24d0`.

Each of our customers gets a different `connection_ref`. Please treat it as an
account-level configuration value.

---

## 3. Authentication

We can support any of the following. **Please tell us which you can send** (question 3 in the
companion document). Listed in our order of preference:

### Option 1 — HMAC signature (preferred)

```
X-FlexCRM-Signature: sha256=<hex>
```

Where `<hex>` is `HMAC-SHA256(shared_secret, raw_request_body)` computed over the **exact bytes**
of the request body, before any parsing or re-encoding.

### Option 2 — Static shared secret header

```
X-FlexCRM-Key: <secret>
```

### Option 3 — Secret in the path

If you cannot send custom headers at all, we can issue a URL where the path segment is itself the
secret. We would rather avoid this (secrets tend to end up in access logs), but it is supported.

We issue the shared secret during onboarding and it is shown to our customer once. It can be
rotated on request without changing the URL.

---

## 4. Request payload

JSON object. Unknown fields are accepted and preserved (appended to the lead's notes) rather than
rejected — so sending us extra data is safe and encouraged.

### Required

| Field | Type | Max | Notes |
|---|---|---|---|
| `lead_id` | string | 128 | **Your permanently unique id for this lead.** This is what makes redelivery safe — see §6. |
| `name` | string | 255 | Enquirer's name |
| `phone` | string | 32 | Preferably E.164 (`+919876543210`). Tell us your actual format. |

### Optional

| Field | Type | Max | Maps to |
|---|---|---|---|
| `email` | string | 255 | Contact email |
| `alt_phone` | string | 32 | Secondary phone |
| `posted_at` | string (ISO 8601) | — | When the enquiry was made on 99acres |
| `account_id` | string | 64 | Your account/client id — used as a routing fallback (§7) |
| `project_name` | string | 255 | Property/project enquired about |
| `listing_id` | string | 64 | Your listing identifier |
| `city` | string | 255 | Combined with `locality` into preferred location |
| `locality` | string | 255 | |
| `property_type` | string | 64 | One of `apartment`, `villa`, `plot`, `commercial` (we map close variants) |
| `configuration` | string | 255 | e.g. `2 BHK`, `3 BHK`, `Studio`, `Plot / Land` |
| `budget_min` | number | — | In INR |
| `budget_max` | number | — | In INR |
| `possession` | string | 64 | e.g. `Ready to move`, `Under construction` |
| `campaign` | string | 120 | Campaign/source sub-attribution |
| `message` | string | — | The enquirer's free-text message |

Values longer than the stated maximum are **truncated, not rejected** — we will never drop a lead
over a length issue.

### Example

```json
{
  "lead_id": "99A-2026-8837421",
  "name": "Ramesh Kumar",
  "phone": "+919876543210",
  "email": "ramesh.kumar@example.com",
  "posted_at": "2026-08-22T14:31:07+05:30",
  "account_id": "VVR-114520",
  "project_name": "Vista Greens Phase 2",
  "listing_id": "L-99283746",
  "city": "Bengaluru",
  "locality": "Whitefield",
  "property_type": "apartment",
  "configuration": "3 BHK",
  "budget_min": 7500000,
  "budget_max": 9000000,
  "possession": "Ready to move",
  "message": "Interested in a site visit this weekend."
}
```

---

## 5. Responses

| Status | Meaning | Should you retry? |
|---|---|---|
| `200` | Accepted and **durably stored** | No |
| `401` / `403` | Missing or invalid credential | No — contact us |
| `404` | Unknown `connection_ref` | No — contact us |
| `422` | Malformed body or a required field missing | No — the response body names the problem |
| `429` | Rate limited | **Yes**, with backoff |
| `5xx` | Our fault | **Yes**, with backoff |

Success body:

```json
{ "status": "accepted", "lead_id": "99A-2026-8837421" }
```

Error body:

```json
{ "error": { "code": "validation_error", "detail": "phone is required." },
  "request_id": "8f21c0d4e5b64a7c", "path": "/api/v1/webhooks/99acres/c_7f3a91be24d0" }
```

Please log `request_id` — quoting it lets us find the exact request instantly.

> **Important:** a `200` means we have **durably stored** your payload, not that the CRM lead is
> fully built. We deliberately acknowledge before processing so that a transient fault on our side
> can never cause you to lose a lead. If processing later fails, we retry it ourselves from the
> stored payload — you never need to resend.

---

## 6. Idempotency and retries

We deduplicate on `lead_id`. **Sending the same `lead_id` again is always safe** — the second and
subsequent deliveries are recognised and ignored, and will still return `200`. Retry freely.

This is why `lead_id` matters so much: it must be stable (the same lead always carries the same id,
including on a retry) and unique (never reused for a different enquiry). If you cannot provide such
an id, tell us — we can fall back to a fingerprint of phone + timestamp, but that is measurably
less reliable and we would rather not.

**Retry policy we would like:** on `429` and `5xx`, retry with exponential backoff for at least
~30 minutes. Please tell us what your platform actually does (question 6).

---

## 7. Routing fallback

Our preferred design gives each account its own URL, so routing is unambiguous.

If your platform can only POST to a **single shared URL** for all your clients, we can instead route
on the `account_id` field in the payload. In that case `account_id` becomes **required**, and each
of our customers registers their 99acres account id with us during onboarding. Please tell us which
model applies (question 2).

---

## 8. Operational notes

- **TLS** — HTTPS only, TLS 1.2+.
- **Timeouts** — we target a p99 response under 500 ms. Please allow at least a 10 s timeout.
- **Volume** — tell us your expected peak (question 8) so we can size limits appropriately. We will
  configure our rate limiting around your stated peak with generous headroom.
- **Source IPs** — if you can give us your egress IP ranges (question 10) we will allowlist them as
  an additional control. Not required.
- **Ordering** — we do not require ordered delivery.
- **Character encoding** — UTF-8 throughout.

---

## 9. Testing

Before go-live we will provide a **sandbox `connection_ref`** pointed at a non-production
workspace, so you can send test traffic freely without creating real CRM records.

```bash
curl -X POST \
  "{BASE_URL}/api/v1/webhooks/99acres/{connection_ref}" \
  -H "Content-Type: application/json" \
  -H "X-FlexCRM-Key: {secret}" \
  -d '{
        "lead_id": "TEST-0001",
        "name": "Test Enquirer",
        "phone": "+919999900000",
        "project_name": "Sandbox Project",
        "city": "Bengaluru"
      }'
```

Expected: `200 {"status":"accepted","lead_id":"TEST-0001"}`.

We would also welcome a "send test lead" trigger on your side if one exists (question 9).

---

## 10. Onboarding a customer — the sequence

1. Our customer enables the 99acres integration in FlexCRM and generates a connection.
2. FlexCRM issues a `connection_ref` + secret.
3. The customer (or we, with their authorisation) passes those to their 99acres account manager.
4. 99acres configures the callback on that account.
5. A test lead is sent and confirmed end to end.
6. Live.

Please tell us who performs step 4 on your side and the expected lead time (question 13).

---

## 11. Contact

*(To be completed before sending — technical contact, escalation path, and preferred channel.)*
