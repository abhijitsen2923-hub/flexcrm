# Adding a new module

A "module" is an optional, per-org feature (e.g. Deals, Tasks, Finance, Inventory). Access is
**granted per org by a platform admin** in Platform Admin — new tenants start with every module
**off** (`organizations.features = None`). A module becomes visible only when **both** layers agree:

```
mergeModules() = FEATURES[key] (platform build flag)  AND  org.modules[key] (admin grant)
```

The wiring below is **identical for every module**, whether it's for *all* business types or a
*specific* one. The **only** business-type-specific part is step 6 (its default + group).

## Checklist

### Frontend
1. **`frontend/src/types/crm.ts`** — add the key to the `ModuleKey` union.
2. **`frontend/src/config/features.ts`** — add it to the `FEATURES` record
   (`flag(import.meta.env.VITE_FEATURE_<NAME>_ENABLED)`) **and** to the `mergeModules` keys array.
3. **`frontend/.env.production`** (and `frontend/.env.example`) — add
   `VITE_FEATURE_<NAME>_ENABLED=true`. Without the platform flag the module never shows, even if
   an admin grants it.
4. **`frontend/src/components/layout/Sidebar.tsx`** — add the nav item with
   `moduleKey: "<name>"` (gates visibility) + `requires: ["<PERMISSION>"]` + icon + route.
5. **Router** — add the page route + component.
6. **`frontend/src/pages/PlatformAdminPage.tsx`** — add the key to a group array
   (`CORE_MODULES` / `OPS_MODULES` / `RE_MODULES`, or a new group) **and** set its default in
   `defaultsForIndustry()`. ← *this is the only business-type-specific line.*

### Backend
7. **`backend/app/schemas/organization.py`** — add the key to `MODULE_KEYS` (the canonical list;
   drives `get_modules()` and the admin `PATCH /admin/organizations/{id}/modules` validation).
8. Add the module's API endpoints + `PermissionCode`s.
9. If the module has **tenant tables**, add a tenant migration under
   `backend/migrations_tenant/versions/`. See the ⚠️ enum rule in that folder's `README.md`.

## The only business-type difference — step 6

```ts
function defaultsForIndustry(industry) {
  return {
    ...,
    myNewModule: true,                       // available to ALL business types
    myREModule: industry === "real_estate",  // only a SPECIFIC business type
  };
}
```

Everything else (steps 1–5, 7–9) is identical.

## Behavior you get for free
- New tenants get the module **off**; the provider grants it in Platform Admin.
- The Dashboard "contact your provider" notice ([DashboardPage.tsx]) auto-covers a tenant with no
  modules — no per-module work.
- `mergeModules` / the `noModules` check iterate all keys, so adding one "just works".
