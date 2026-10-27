# Tenant Subscription Payment Reminder

## Overview
FlexCRM allows platform administrators (SaaS owners) to display a prominent payment reminder notification banner at the very top of staff screens for any client organization nearing subscription expiration or renewal.

**Client Banner Notice:**
> *"Your subscription is about to end in {days}. Kindly contact with your provider for make the paymant to use the application semmlessly."*

---

## Behavior & Lifecycle

### 1. Prominent Top Screen Banner
- Mounted globally in `frontend/src/components/layout/AppLayout.tsx` via `<SubscriptionReminderBanner />` directly above `<Topbar />`.
- Visible across all staff console routes and pages (`Dashboard`, `Leads`, `Bookings`, `Finance`, `Customers`, etc.).
- **Urgency Matrix:**
  - `> 3 days`: Warm amber warning banner.
  - `1 – 3 days`: High-urgency alert.
  - `0 or expired`: High-contrast critical alert banner.

### 2. Close & Re-appearance Lifecycle
- When a staff member clicks the close `[X]` button on the banner, it dismisses for their current view.
- Dismissal is maintained strictly in component state (in-memory).
- **Upon page refresh (F5), browser reload, or re-login**, the component remounts, state resets to `dismissed = false`, and the banner reappears immediately.

### 3. Provider Contact Details
- Platform admins can configure custom contact details (e.g. `billing@flexcrm.io | +91 98765 43210`).
- Staff can click **"Contact Provider"** to open a modal displaying the exact billing contact channel without disrupting their work.

### 4. Responsive Mobile Design
- On desktop view, the notification renders as a sleek top bar with inline action buttons.
- On mobile viewports (`< 640px`), the banner automatically transitions into a stacked layout (`flex-direction: column`):
  - Notice text wraps completely across lines without truncation (`overflow-wrap: anywhere; word-break: break-word`).
  - Action buttons ("Contact Provider", dismiss `[X]`) span cleanly at the bottom for easy touch access.

---

## Platform Admin Controls (`/admin`)

Located in `frontend/src/pages/PlatformAdminPage.tsx` under each client organization card:
- **Payment Reminder Toggle:** Enable / disable the banner in one click.
- **Subscription End Date:** Native date picker with live calculation of remaining days.
- **Provider Contact Info:** Text input for email / phone / contact information.
- **Save Reminder Button:** Persists immediately to the backend and clears tenant cache.

---

## Data Model & API Specification

### 1. Data Storage
Stored inside `public.organizations.features["subscription"]`:
```json
{
  "reminder_enabled": true,
  "end_date": "2026-11-05",
  "provider_contact": "billing@flexcrm.io | +91 98765 43210"
}
```
*Zero database migrations required; seamlessly preserved during tenant updates.*

### 2. Endpoints
- **Update Subscription Config (Platform Admin Only):**
  - `PATCH /api/v1/admin/organizations/{org_id}/subscription`
  - Guarded by `require_platform_admin()`.
  - Automatically invalidates `schema:{org_id}` in Redis cache.
- **Get Tenant Organization (Tenant Staff):**
  - `GET /api/v1/organizations/me`
  - Returns `OrganizationRead` containing `subscription: SubscriptionConfig`.

---

## Verification & Automated Tests
- **Backend Test:** `backend/tests/test_subscription_reminder.py` (Validates 403 authorization guard, admin updates, and tenant retrieval).
- **Frontend Test:** `frontend/tests/subscriptionReminder.test.ts` (Validates date diffs, boundary dates, and negative/expired handling).

