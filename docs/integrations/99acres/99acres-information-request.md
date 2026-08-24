# 99acres → FlexCRM integration — information request

**To:** 99acres integration team
**From:** FlexCRM
**Companion document:** `flexcrm-lead-api.md` (our endpoint specification)

Thank you for agreeing to integrate. We have specified our side in the companion document. The
questions below are what we need from you to finalise it.

They are ordered so that **1–4 are blocking** — we cannot finish the build without them. The rest
we can design around, but each answer removes a guess.

Please answer inline; a short reply per item is fine.

---

## Blocking

### 1. Is there a permanently unique lead id in your payload?

This is our single most important question.

We deduplicate on an id you send us, so that a retry or a duplicate delivery can never create a
duplicate lead in our customer's CRM.

- What is the field called?
- What is its format and maximum length?
- Is it stable across retries of the same lead?
- Is it guaranteed never to be reused for a different enquiry?

> **If no such id exists**, please say so explicitly. We would then have to fingerprint each lead
> from phone + timestamp, which is measurably less reliable and can drop genuine repeat enquiries
> from the same person. We would like to avoid that.

**Answer:**

---

### 2. One URL per account, or one shared URL for everyone?

Our customers each hold their own 99acres account. Can your platform POST to a **different callback
URL per account** (our preference — it makes routing unambiguous), or do you deliver all clients'
leads to a **single URL** we register once?

If it is a single shared URL, we will need a reliable account identifier in every payload so we can
tell which of our customers a lead belongs to.

**Answer:**

---

### 3. What authentication can you send?

Please tick everything your platform supports:

- [ ] HMAC signature over the request body in a custom header (our preference)
- [ ] A static secret in a custom header (e.g. `X-FlexCRM-Key`)
- [ ] HTTP Basic authentication
- [ ] Mutual TLS
- [ ] A secret embedded in the URL path or query string
- [ ] IP allowlisting only — no credential
- [ ] **Can you send custom request headers at all?** Yes / No

**Answer:**

---

### 4. Exact payload schema, plus one real sample

- Is the body JSON, or form-encoded?
- The full field list with types, and which are guaranteed present versus optional.
- Character encoding.
- **Phone number format** — E.164 (`+919876543210`), 10-digit local, or something else? Are country
  codes always present?
- Are values ever `null`, empty strings, or absent keys — and do those mean different things?

A real (redacted) sample payload is worth more than a schema document. Please attach one if you can.

**Answer:**

---

## Important

### 5. Do you offer any pull or export API?

Even a once-daily "leads since timestamp" endpoint would let us reconcile and self-heal if a
webhook delivery is ever missed. Webhook-only integrations have no way to detect a lead that never
arrived.

If such an API exists, we would like its documentation and auth details. This meaningfully reduces
the risk of a lost lead for our shared customers.

**Answer:**

---

### 6. What is your retry policy?

- Which response codes trigger a retry?
- How many attempts, over what period, with what backoff?
- What request timeout do you apply?
- Is there a dead-letter or alerting mechanism if all retries fail, and can our customer see it?

**Answer:**

---

### 7. Duplicate and out-of-order delivery

- Can the same lead be delivered more than once in normal operation (not just on retry)?
- Can leads arrive out of chronological order?

**Answer:**

---

### 8. Expected volume

- Typical leads per day for a single account.
- Realistic peak burst — e.g. during a campaign or a portal-side backlog flush.

We will size our rate limits around your stated peak. Getting this right avoids us throttling you.

**Answer:**

---

### 9. Sandbox and test tooling

- Is there a staging/sandbox environment we can integrate against first?
- Is there a "send test lead" button or API so we can verify a connection end to end without
  waiting for a real enquiry?

**Answer:**

---

### 10. Source IP ranges

Do you publish egress IP ranges for your outbound webhooks? We would allowlist them as an extra
control. Not required, and we understand if they are not static.

**Answer:**

---

## Good to know

### 11. Property and campaign identifiers

Do your payloads carry project, listing, or campaign identifiers? Our customers want to know which
listing produced each lead, so anything you can send here is valuable.

**Answer:**

---

### 12. Historical backfill

When one of our customers first connects, can we retrieve their recent historical leads (say the
last 30–90 days), or does delivery only start from the moment the callback is configured?

**Answer:**

---

### 13. Per-account onboarding process

- Who configures the callback URL for a given account — the account holder themselves in a
  self-serve portal, or your support/account-management team?
- What is the typical lead time?
- Is there a form or ticket process we should tell our customers to follow?

This determines how we word the setup instructions inside our product.

**Answer:**

---

### 14. Certification or review

Is there a technical review, certification, or approval step before an integration is allowed to go
live? If so, what does it involve and how long does it take?

**Answer:**

---

### 15. Data deletion and consent

- Do you send any deletion, opt-out, or do-not-contact notifications we are required to honour?
- Are there contractual constraints on how long we may retain lead data, or on onward processing?

**Answer:**

---

### 16. Contacts

- Technical contact for the integration build.
- Escalation path for production incidents (and hours of cover).
- Preferred channel — email, shared Slack, ticketing system?

**Answer:**

---

## What we need from you to go live — summary

1. Confirmation of the auth method (question 3).
2. The payload schema and a sample (question 4).
3. The unique lead id field (question 1).
4. Sandbox access (question 9).
5. The onboarding process for our customers' accounts (question 13).

## What you need from us

Everything is in the companion document `flexcrm-lead-api.md`. In short: per-account endpoint URL,
shared secret, payload contract, response codes, and a sandbox endpoint for testing. We can issue
sandbox credentials as soon as you confirm question 3.
