"""Multi-tenant scoping primitives.

Three pieces:

1. **`OrgScopedMixin`** — a SQLAlchemy mixin that every domain model inherits.
   Declares a `organization_id` FK column to `organizations.id`. Models opt in
   by adding the mixin; staying out (e.g. PipelineStage, RefreshToken) is also
   a deliberate choice.

2. **Global SELECT filter** — a `do_orm_execute` event listener that injects
   `organization_id = current_org_id` into every ORM-driven SELECT, via
   `with_loader_criteria`. Works for joins and nested loads too.

3. **Auto-populate on flush** — a `before_flush` event listener that fills
   `organization_id` on freshly-added rows that didn't get it explicitly.
   Saves every service.create call from having to pass it manually.

The "current org" is stored on `session.info["organization_id"]`. The auth
dependency (`get_current_user`) injects it on every request. Tests and
system jobs that need to read across orgs set `session.info["bypass_tenancy"]
= True` to short-circuit both listeners.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from uuid import UUID

from sqlalchemy import ForeignKey, Uuid, event
from sqlalchemy.orm import Mapped, Session, mapped_column, with_loader_criteria

# Models registered for tenant scoping. Populated at import time as each
# domain model imports `OrgScopedMixin`. Keeping a registry (rather than
# reflecting metadata on every query) keeps the filter cheap.
SCOPED_MODELS: list[type] = []


class OrgScopedMixin:
    """Adds an `organization_id` FK and registers the model for global scoping."""

    organization_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # `OrgScopedMixin` is mixed into concrete model classes. SQLAlchemy
        # also creates abstract subclasses for inheritance, but every domain
        # model is concrete, so we register on every subclass and de-dupe.
        if cls not in SCOPED_MODELS:
            SCOPED_MODELS.append(cls)


def current_org(session: Session) -> UUID | None:
    return session.info.get("organization_id")


def is_bypassed(session: Session) -> bool:
    return bool(session.info.get("bypass_tenancy"))


def set_scope(session: Session, organization_id: UUID | None) -> None:
    """Set or clear the current org for this session. Used by auth + jobs."""
    if organization_id is None:
        session.info.pop("organization_id", None)
    else:
        session.info["organization_id"] = organization_id


@contextmanager
def bypass(session: Session) -> Iterator[None]:
    """Run a block with the tenancy filter disabled.

    Use for system jobs that iterate across orgs, and for the login path
    that must look up a user by email before its org is known.
    """
    previous = session.info.get("bypass_tenancy", False)
    session.info["bypass_tenancy"] = True
    try:
        yield
    finally:
        session.info["bypass_tenancy"] = previous


# --- Listeners ------------------------------------------------------------


def _apply_select_filter(execute_state) -> None:
    """Filter every ORM SELECT to the current org via with_loader_criteria."""
    session = execute_state.session
    if is_bypassed(session):
        return
    org_id = current_org(session)
    if org_id is None:
        # Unscoped session — no filter. Auth handlers operate in this mode
        # for the brief window before the user is resolved.
        return

    # Relationship loads (e.g. lead.customer) should not be re-filtered, since
    # the parent row already passed the filter; re-filtering can blank out
    # legitimate links if the FK target row is in the same org.
    if execute_state.is_relationship_load:
        return
    if not execute_state.is_select:
        return

    # CRITICAL: pass the org as a real expression (not via default-arg trick).
    # `with_loader_criteria` participates in SQLAlchemy's compiled-statement
    # cache; default args aren't tracked as closure variables, so a lambda
    # with `_org=org_id` would freeze the FIRST org's id into the cached SQL
    # and return that org's data on every subsequent request. Building the
    # criterion as `model.organization_id == org_id` produces a properly
    # parameterized expression that rebinds per query.
    for model in SCOPED_MODELS:
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                model,
                model.organization_id == org_id,
                include_aliases=True,
            )
        )


def _autopopulate_on_flush(session, flush_context, instances) -> None:
    """Stamp organization_id on freshly-added rows from session.info."""
    if is_bypassed(session):
        return
    org_id = current_org(session)
    if org_id is None:
        return

    for obj in session.new:
        if not isinstance(obj, tuple(SCOPED_MODELS)):
            continue
        if getattr(obj, "organization_id", None) is None:
            obj.organization_id = org_id


def register_listeners() -> None:
    """Wire the two listeners onto the global Session class.

    Idempotent — called once at app startup. SQLAlchemy event listeners are
    attached on the class, not per-session, so this runs once for the
    lifetime of the process.
    """
    if getattr(register_listeners, "_done", False):
        return
    event.listen(Session, "do_orm_execute", _apply_select_filter)
    event.listen(Session, "before_flush", _autopopulate_on_flush)
    register_listeners._done = True  # type: ignore[attr-defined]
