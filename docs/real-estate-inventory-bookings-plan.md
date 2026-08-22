# Plan (COMPLETED): Real-estate inventory & bookings completion

Status: **done** — kept as a historical record of the gap and how it was closed.
Originally deferred 2026-07-02; the work has since shipped.

Where it landed:
- Tower create → `POST /inventory/projects/{project_id}/towers`
- Unit batch create → `POST /inventory/towers/{tower_id}/units/batch`
  (plus `PATCH`/`DELETE` for towers and units)
- UI → the tower/unit manager in `frontend/src/pages/inventory/ProjectsPage.tsx`
- "New Booking" → wired in `frontend/src/pages/bookings/BookingsPage.tsx`

Everything below is the original 2026-07-02 plan text, unedited.

## The gap

The real-estate module is scaffolded end-to-end on the UI but the middle of the
inventory hierarchy has **no create path**, so bookings can't function:

- **Projects** — ✅ create works (`POST /inventory/projects`, and the Add Project
  modal in `frontend/src/pages/inventory/ProjectsPage.tsx`).
- **Towers** — ❌ no backend endpoint, no UI. Table exists (tenant migration
  `t002`) but nothing can insert rows.
- **Units** — ❌ no create endpoint (only `GET /inventory/units/{id}` and
  `PATCH /inventory/units/{id}/status`). Table exists (`t002`).
- **Bookings** — `POST /bookings` exists but requires a `unit_id`. The
  `BookingWizard` (`frontend/src/pages/bookings/components/BookingWizard.tsx`) is
  unit-centric and is normally reached from the Inventory board via `?unitId=`.
- **"New Booking" button** (`BookingsPage.tsx`) has no `onClick` — intentionally
  left dead until inventory creation exists, since there are no units to book.

Net effect: a fresh tenant can create a project but never add towers/units, so
there is nothing to book.

## Build plan

### Backend (`app/real_estate/`)
1. **Schemas** (`schemas.py`):
   - `TowerCreate { name, total_floors }`
   - `UnitCreate { tower_id, floor, unit_number, area, area_unit="sqft", facing?, view?, base_price }`
   - `UnitBulkCreate { tower_id, floor_from, floor_to, units_per_floor, area, base_price, unit_number_prefix? }`
     → server generates `floors × units_per_floor` units (e.g. `A-<floor><nn>`),
     status defaults `available`.
2. **Endpoints** (`router.py`), gated `PermissionCode.LEAD_MANAGE` (same as project create):
   - `POST /inventory/projects/{project_id}/towers` → create tower.
   - `POST /inventory/towers/{tower_id}/units` → create one unit **or** bulk
     generate (accept `UnitCreate` or `UnitBulkCreate`).
   - (optional) `PATCH`/`DELETE` for towers/units.
   - Reuse the existing add/commit/refresh pattern; tenant schema routing is
     already handled by the `do_orm_execute` + `after_begin` listeners.
3. Models `Tower`/`Unit` already exist (`models.py`, migration `t002`) — no DB
   change needed.

### Frontend
1. **`services/inventory.ts`** — add `createTower(projectId, payload)` and
   `createUnits(towerId, payload)`; map snake↔camel like the existing helpers.
2. **Project detail modal** (`ProjectsPage.tsx`) — add:
   - "Add tower" form (name, total floors) + list of towers.
   - Per tower: "Add units" with the bulk generator (floors range, units/floor,
     area, base price) + a units table showing status.
3. **`BookingsPage.tsx`** — wire "New Booking":
   - Open a **unit picker** modal: Project → Tower → available Unit (filter
     `status === "available"`).
   - On select, build the enriched unit `{ id, unitNumber, floor, area,
     basePrice, towerName, projectName }` and open `BookingWizard`.
   - Empty state when no available units ("Add units to a project first").
4. After booking completes, `refresh()` the list (already wired).

### Follow-up polish
- `BookingWizard` step 2 uses a raw "Customer ID" text field — replace with a
  customer search/picker.
- Inventory board (`pages/inventory/components/InventoryBoard.tsx`) should link a
  unit's "Book" action to `/bookings?unitId=<id>` (the wizard already supports
  the `?unitId=` deep link).

## Verify (when built)
Fresh real-estate tenant → create project → add tower → bulk-add units →
Inventory shows available units → New Booking → pick unit → wizard → confirm →
booking appears in the list; unit status flips to `booked`.
