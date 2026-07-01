# Tenant migrations

These migrations run **once per tenant schema** (via `provision_tenant()` at registration, and
through the Alembic chain for new tenants). The active schema is set through `search_path` /
`schema_translate_map` by `env.py` before each migration runs.

## ⚠️ Enum columns MUST bind to the public enum type

All enum *types* are created once in the **public** schema by the shared (`migrations/`)
migrations. Tenant tables must **reference** those public types — they must **not** create a
local copy.

**Always use `postgresql.ENUM(..., create_type=False, schema="public")`. Never `sa.Enum(...)`.**

```python
from sqlalchemy.dialects import postgresql

# CORRECT — binds to public.deal_status_enum, no local copy:
sa.Column(
    "status",
    postgresql.ENUM("open", "won", "lost", "on_hold",
                    name="deal_status_enum", create_type=False, schema="public"),
    nullable=False,
)

# WRONG — sa.Enum ignores create_type=False and creates a tenant-LOCAL
# <schema>.deal_status_enum that shadows the public one. Queries then fail with:
#   operator does not exist: <schema>.deal_status_enum = deal_status_enum
# on any status filter (any =/IN comparison), 500-ing dashboard/analytics.
sa.Column("status", sa.Enum(..., name="deal_status_enum", create_type=False), nullable=False)
```

If you add a new enum, first create the type in a **public** migration (`migrations/versions/`),
then reference it here with `postgresql.ENUM(..., schema="public")`.

See `docs/adding-a-module.md` for the full "add a module" checklist.
