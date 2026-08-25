# FlexCRM — Lead Ingestion API

**For:** 99acres integration team
**Status:** Final — v1.0
**Companion document:** `99acres-information-request.md` (a few operational details we'd still like)

> This document specifies the endpoint 99acres calls to deliver leads into FlexCRM. The design is
> settled. It is built to accept your **existing lead-export fields as-is** — you JSON-encode a lead and
> POST it; we do all the parsing on our side.

---

## 1. Overview

FlexCRM is a multi-tenant CRM. Each of our customers (a builder or brokerage) holds **their own
99acres account**, and each gets their **own dedicated endpoint URL** from us.

From your side the model is simply: *one 99acres account → one URL*, issued by us during onboarding.
There is nothing else to configure — no header, no key entry. The URL itself is the credential (§3).

```
99acres  ──POST new lead──►  FlexCRM endpoint (unique per account)
                             │
                             ├─ authenticate (the URL token)
                             ├─ store the raw payload durably
                             ├─ respond 200
                             └─ create the CRM lead (async)
```

---

## 2. Endpoint

```
POST {BASE_URL}/api/v1/webhooks/99acres/{token}
Content-Type: application/json; charset=utf-8
```

- `{BASE_URL}` — currently `https://flexcrm-backend-539170436218.asia-south1.run.app`. A branded custom
  domain may replace this before go-live; we will give you the final value in writing and support both
  for a transition period.
- `{token}` — a long, random, **secret** value we issue per 99acres account (example:
  `c_7f3a91be24d0a1b2c3d4e5f6`). It both identifies the account and authenticates the request, so **the
  full URL must be kept private** — treat it like a password. Each of our customers gets a different
  token, so each account has a different URL.

---

## 3. Authentication

**The URL token is the credential — that is the whole scheme.** A request to a valid, active token is
authenticated; there is no separate header or signature to send.

- The token carries ~190 bits of entropy, so it cannot be guessed.
- HTTPS only (TLS 1.2+), so the URL is encrypted in transit.
- We scrub the token from our access logs and can **rotate** it on request (we issue a new URL; the old
  one stops working) without any other change on your side.
- Optional, if you can provide it: give us your egress IP ranges (companion doc) and we will allowlist
  them as an extra layer. Not required.

If you would prefer to *also* send a secret header or an HMAC signature, we can enable that per account —
tell us and we'll document it. It is not needed by default.

---

## 4. Request payload

A JSON object. **Send your standard lead-export fields using your own field names** — you do not need to
rename anything. We recognise the fields below; **any field we don't recognise is preserved** (appended to
the lead's notes), so sending extra data is safe and encouraged.

### Required

| Field | Type | Notes |
|---|---|---|
| `lead_id` | string | **Your permanently unique id for this lead, if your system has one.** This is the best dedupe key — see §6. If you cannot provide one, omit it and we fall back to a fingerprint (§6). |
| `Name` | string | Enquirer's name |
| `ContactNo` | string | Phone. Your `91-9876543210` format (country code, hyphen, 10 digits) is fine — we normalise it. |

### Recognised optional fields (your export column names)

| Field | Example | How we use it |
|---|---|---|
| `EmailId` | `ramesh@example.com` | Contact email (often blank — fine) |
| `InterestedIn` | `Vriddhica Heritage\|Joka\|Kolkata South` | We split on `\|` into **Project / Locality / City** |
| `City` | `Kolkata South` | Preferred location |
| `ResCom` | `R` | `R` = residential, `C` = commercial |
| `Bhk` | `3 BHK` | Configuration |
| `Query` | `I am interested in this Project.` | The enquirer's message |
| `ProductCode` | `4928148` | Your listing id (used in the fingerprint, §6, and kept for attribution) |
| `ReceivedDate` | `07/13/2026 12:39 AM` | When the enquiry was made (`MM/DD/YYYY hh:mm AM/PM`) |
| `Username` / `AssignedTo` | `vridhhilandmart@99acres.com` / `Vriddhi Landmart Ltd` | Your account identifier — we use it as a sanity check |
| `Type` | `Individual` / `Dealer` | Kept for context |
| `LeadScore` | `3.5` | Kept for context |
| `ResponseType` | `QUERY` / `C2V` | Kept for context |
| `ProductType`, `ProdType`, `FollowupCurrentStatus`, `Duplicate`, `PhoneVerificationStatus`, … | | Kept for context (appended to notes) |

Character encoding is **UTF-8**. Values longer than our column limits are **truncated, not rejected** — we
will never drop a lead over a length issue.

### Example (a real export row, phone redacted)

```json
{
  "lead_id": "",
  "Name": "Susanta Bhattacharjee",
  "ContactNo": "91-98304XXXXX",
  "EmailId": "",
  "Query": "I am interested in this Project.",
  "ReceivedDate": "07/13/2026 12:39 AM",
  "InterestedIn": "Vriddhica Heritage|Joka|Kolkata South",
  "City": "Kolkata South",
  "ResCom": "R",
  "Bhk": "",
  "ProductCode": "4928148",
  "ProductType": "NEW NP",
  "Type": "Individual",
  "LeadScore": "3.5",
  "ResponseType": "QUERY",
  "PhoneVerificationStatus": "VERIFIED",
  "Username": "vridhhilandmart@99acres.com",
  "AssignedTo": "Vriddhi Landmart Limited"
}
```

---

## 5. Responses

| Status | Meaning | Should you retry? |
|---|---|---|
| `200` | Accepted and **durably stored** | No |
| `401` / `403` | Invalid or inactive URL token | No — contact us |
| `404` | Unknown token | No — contact us |
| `422` | Malformed body, or `Name`/`ContactNo` missing | No — the response body names the problem |
| `429` | Rate limited | **Yes**, with backoff |
| `5xx` | Our fault | **Yes**, with backoff |

Success body:

```json
{ "status": "accepted", "lead_id": "99A-2026-8837421" }
```

Error body:

```json
{ "error": { "code": "validation_error", "detail": "ContactNo is required." },
  "request_id": "8f21c0d4e5b64a7c", "path": "/api/v1/webhooks/99acres/c_7f3a91be24d0" }
```

Please log `request_id` — quoting it lets us find the exact request instantly.

> **Important:** a `200` means we have **durably stored** your payload, not that the CRM lead is fully
> built. We deliberately acknowledge before processing so a transient fault on our side can never cause
> you to lose a lead. If processing later fails we retry it ourselves from the stored payload — you never
> need to resend.

---

## 6. Idempotency and retries

**Sending the same lead again is always safe** — duplicates are recognised and ignored, and still return
`200`. Retry freely.

How we deduplicate:
- **If you send `lead_id`** — we dedupe on it. This is the most reliable key; please send it if your
  system has a stable per-lead id (the same lead must always carry the same id, and an id is never reused
  for a different enquiry).
- **If you don't** — we derive a fingerprint from **normalised `ContactNo` + `ReceivedDate` +
  `ProductCode`** and dedupe on that. This makes redelivery of the *same* enquiry safe; a genuine new
  enquiry from the same person (different `ReceivedDate`) is treated as a new lead, which is what you want.

**Retry policy we'd like:** on `429` and `5xx`, retry with exponential backoff for at least ~30 minutes.

---

## 7. Routing

Each account has its own URL, so routing is unambiguous — the token in the path tells us exactly which
account (and which of our customers) a lead belongs to. We do **not** rely on any field in the body for
routing; `Username`/`AssignedTo` are only a sanity check.

---

## 8. Operational notes

- **TLS** — HTTPS only, TLS 1.2+.
- **Timeouts** — we target a p99 response under 500 ms. Please allow at least a 10 s timeout.
- **Volume** — tell us your expected peak (companion doc) so we can size limits with generous headroom.
- **Ordering** — we do not require ordered delivery.
- **Character encoding** — UTF-8 throughout.

---

## 9. Testing

Before go-live we provide a **sandbox token** pointed at a non-production workspace, so you can send test
traffic freely without creating real CRM records.

```bash
curl -X POST \
  "{BASE_URL}/api/v1/webhooks/99acres/{token}" \
  -H "Content-Type: application/json" \
  -d '{
        "lead_id": "TEST-0001",
        "Name": "Test Enquirer",
        "ContactNo": "91-9999900000",
        "InterestedIn": "Sandbox Project|Whitefield|Bengaluru",
        "City": "Bengaluru",
        "ResCom": "R",
        "Query": "Test lead."
      }'
```

Expected: `200 {"status":"accepted","lead_id":"TEST-0001"}`.

A "send test lead" trigger on your side, if one exists, would be welcome (companion doc).

---

## 10. Onboarding a customer — the sequence

1. Our customer enables the 99acres integration in FlexCRM and generates a connection.
2. FlexCRM issues the unique URL (with its secret token).
3. The customer (or we, with their authorisation) passes that URL to their 99acres account manager.
4. 99acres configures the callback on that account.
5. A test lead is sent and confirmed end to end.
6. Live.

Please tell us who performs step 4 on your side and the expected lead time (companion doc).

---

## 11. Contact

*(To be completed before sending — technical contact, escalation path, and preferred channel.)*
