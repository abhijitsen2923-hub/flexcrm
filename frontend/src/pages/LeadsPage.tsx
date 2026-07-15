import { Download, LayoutGrid, List as ListIcon, Plus, RefreshCw, Upload } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent, type FormEvent } from "react";

import {
  Badge,
  Button,
  DataTable,
  EmptyState,
  LoadingBlock,
  Modal,
  Pagination,
  SelectField,
  TextField,
  useToast,
  type DataTableColumn
} from "../components";
import { LeadDrawer } from "../components/leads/LeadDrawer";
import { StageTransitionModal } from "../components/leads/StageTransitionModal";
import { usePipelines } from "../context/PipelineContext";
import { useAuth } from "../hooks/useAuth";
import { useLeads } from "../hooks/useLeads";
import { usePermissions } from "../hooks/usePermissions";
import { useRealtimeEvent } from "../realtime";
import { exportsService } from "../services/exports";
import { leadsService, type LeadDuplicate, type LeadImportResult } from "../services/leads";
import { organizationsService } from "../services/organizations";
import { siteVisitsService } from "../services/site-visits";
import { usersService } from "../services/users";
import type { Lead, LeadIndustry, Organization, PipelineStage, User } from "../types";
import { extractErrorMessage } from "../utils/errors";
import { formatCurrency } from "../utils/format";
import { OTHER_OPTION, industryInterestLabel, leadIndustryOptions, leadSourceOptions, pipelineCategoryTone, propertyInterestOptions, titleCase } from "../utils/options";


type ViewMode = "list" | "kanban";


// Red "!" marker shown on any lead that shares an email or phone with another
// active lead (backend sets `is_duplicate` on the list response).
function DuplicateMark() {
  return (
    <span
      title="Possible duplicate — shares an email or phone with another lead"
      aria-label="Possible duplicate lead"
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 16,
        height: 16,
        borderRadius: "50%",
        background: "#dc2626",
        color: "#fff",
        fontSize: 11,
        fontWeight: 800,
        lineHeight: 1,
        flexShrink: 0
      }}
    >
      !
    </span>
  );
}


interface CreateFormState {
  industry: LeadIndustry;
  title: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  contact_phone_alt: string;
  company_name: string;
  value: string;
  currency: string;
  probability: string;
  expected_close_date: string;
  source: string;
  source_other: string;
  interest: string;
  interest_other: string;
  // Real-estate specific (only submitted when industry === "real_estate")
  property_type: string;
  property_type_other: string;
  budget_min: string;
  budget_max: string;
  preferred_location: string;
  possession_preference: string;
}


function makeEmptyForm(
  defaultIndustry: LeadIndustry = "education",
  defaultCurrency: string = "INR"
): CreateFormState {
  return {
    industry: defaultIndustry,
    title: "",
    contact_name: "",
    contact_email: "",
    contact_phone: "",
    contact_phone_alt: "",
    company_name: "",
    value: "0",
    currency: defaultCurrency,
    probability: "0",
    expected_close_date: "",
    source: "",
    source_other: "",
    interest: "",
    interest_other: "",
    property_type: "",
    property_type_other: "",
    budget_min: "",
    budget_max: "",
    preferred_location: "",
    possession_preference: ""
  };
}


export default function LeadsPage() {
  const { user } = useAuth();
  // Scope the user's default view to the industry they picked at registration.
  // `business_type` may be null on legacy accounts created before that column
  // existed — fall back to no filter so they keep seeing everything.
  const defaultIndustry: LeadIndustry | "" = user?.business_type ?? "";

  const [view, setView] = useState<ViewMode>("list");
  const [page, setPage] = useState(1);
  const [industryFilter, setIndustryFilter] = useState<LeadIndustry | "">(defaultIndustry);
  const [stageFilter, setStageFilter] = useState<string>("");

  // If the auth context resolves AFTER the first render (it does — there's an
  // initial profile fetch), pick up the business_type once it lands.
  useEffect(() => {
    if (user?.business_type && industryFilter === "") {
      setIndustryFilter(user.business_type);
    }
    // intentionally only react to business_type changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.business_type]);

  // Fetch the user's organization once to get its allowed_currencies. The
  // currency dropdown in the New Lead form lists exactly these codes — for
  // an Education org that's [INR, USD]; Travel orgs get [INR, USD, EUR].
  const [org, setOrg] = useState<Organization | null>(null);
  useEffect(() => {
    let cancelled = false;
    void organizationsService
      .me()
      .then((value) => {
        if (!cancelled) setOrg(value);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  const allowedCurrencies = useMemo(
    () => (org?.allowed_currencies?.length ? org.allowed_currencies : ["INR"]),
    [org]
  );

  const query = useMemo(
    () => ({
      page,
      page_size: 20,
      industry: industryFilter || undefined,
      stage_code: stageFilter || undefined
    }),
    [page, industryFilter, stageFilter]
  );

  const { leads, pagination, loading, refresh, createLead, transitionLead } = useLeads(query);
  const { byIndustry, stages: allStages, getStage } = usePipelines();
  const { has: hasPerm } = usePermissions();
  const canManage = hasPerm("LEAD_MANAGE");
  const canImport = hasPerm("LEAD_IMPORT");
  const canExport = hasPerm("EXPORT_DATA");
  // Assigning a lead owner is an admin/manager capability: it needs to see the
  // team, so gate it on USER_VIEW (owner/admin/manager have it; sales reps don't).
  const canAssign = hasPerm("USER_VIEW");
  const toast = useToast();

  // Auto-refresh when any lead.* envelope arrives — covers create, update,
  // stage_changed, deleted. The dependency array is empty in useRealtimeEvent
  // (it subscribes once), but it always has the latest `refresh` via a ref.
  useRealtimeEvent((event) => {
    if (event.event.startsWith("lead.")) {
      void refresh();
    }
  });

  const stageOptionsForFilter = useMemo(() => {
    const source = industryFilter ? byIndustry[industryFilter] : allStages;
    return source.map((stage) => ({
      value: stage.code,
      label: industryFilter ? stage.name : `${titleCase(stage.industry)} · ${stage.name}`
    }));
  }, [industryFilter, byIndustry, allStages]);

  // --- Create lead modal -------------------------------------------------
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState<CreateFormState>(() => makeEmptyForm(user?.business_type ?? "education"));
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Warn-but-allow duplicate detection (by email or phone, per-tenant).
  const [duplicates, setDuplicates] = useState<LeadDuplicate[]>([]);
  const [dupChecked, setDupChecked] = useState(false);

  // Users in this workspace, for the inline owner-assign dropdown.
  const [assignableUsers, setAssignableUsers] = useState<User[]>([]);
  useEffect(() => {
    if (!canAssign) return;
    let cancelled = false;
    // page_size is capped at 100 server-side (422 above that).
    void usersService
      .list({ page_size: 100 })
      .then((res) => { if (!cancelled) setAssignableUsers(res.items); })
      .catch((err) => { if (!cancelled) toast.error("Couldn't load users", extractErrorMessage(err)); });
    return () => { cancelled = true; };
  }, [canAssign]);

  async function handleAssign(lead: Lead, userId: string | null) {
    try {
      await leadsService.update(lead.id, { assigned_to_id: userId });
      await refresh();
      toast.success("Owner updated", userId ? "Lead assigned." : "Lead unassigned.");
    } catch (err) {
      toast.error("Assign failed", extractErrorMessage(err));
    }
  }

  // --- Bulk reassignment (Manager) ---------------------------------------
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkOwner, setBulkOwner] = useState("");
  const [bulkReassigning, setBulkReassigning] = useState(false);
  const allPageSelected = leads.length > 0 && leads.every((l) => selectedIds.has(l.id));

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  function toggleSelectAllOnPage() {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (leads.every((l) => prev.has(l.id))) leads.forEach((l) => next.delete(l.id));
      else leads.forEach((l) => next.add(l.id));
      return next;
    });
  }
  async function handleBulkReassign() {
    if (!bulkOwner || selectedIds.size === 0) return;
    setBulkReassigning(true);
    try {
      const count = selectedIds.size;
      await leadsService.bulkReassign(Array.from(selectedIds), bulkOwner);
      toast.success("Owner updated", `Reassigned ${count} lead${count === 1 ? "" : "s"}.`);
      setSelectedIds(new Set());
      setBulkOwner("");
      await refresh();
    } catch (err) {
      toast.error("Reassign failed", extractErrorMessage(err));
    } finally {
      setBulkReassigning(false);
    }
  }

  function openCreate() {
    setForm(makeEmptyForm(user?.business_type ?? "education", allowedCurrencies[0] ?? "INR"));
    setFormError(null);
    setDuplicates([]);
    setDupChecked(false);
    setFormOpen(true);
  }

  // An edit to email/phone means we must re-check before creating.
  function resetDupCheck() {
    setDupChecked(false);
    setDuplicates([]);
  }

  function openExistingLead(dup: LeadDuplicate) {
    const found = leads.find((lead) => lead.id === dup.id);
    setFormOpen(false);
    if (found) {
      setDrawerLead(found);
    }
  }

  async function handleCreateSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Mandatory controlled fields (meeting: prevent free-text fragmentation).
    const resolvedSource = form.source === OTHER_OPTION ? form.source_other.trim() : form.source;
    const resolvedInterest = form.interest === OTHER_OPTION ? form.interest_other.trim() : form.interest.trim();
    if (!resolvedSource) {
      setFormError("Please select a valid Source.");
      return;
    }
    if (form.industry === "real_estate" && !resolvedInterest) {
      setFormError("Please select a valid Property Interest.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      // First submit: check for a duplicate lead by email/phone. If any exist,
      // surface them and let the user decide — a second click creates anyway.
      if (!dupChecked) {
        const matches = await leadsService.checkDuplicates(
          form.contact_email.trim() || null,
          form.contact_phone.trim() || null
        );
        setDupChecked(true);
        if (matches.length > 0) {
          setDuplicates(matches);
          return; // finally resets `submitting`; wait for "Create anyway"
        }
      }
      await createLead({
        // Industry is inherited from the logged-in user's business_type on
        // the backend. We don't ask in the form (single-vertical accounts);
        // only fall through with an explicit value if the user has none set.
        ...(user?.business_type ? {} : { industry: form.industry }),
        title: form.title.trim(),
        contact_name: form.contact_name.trim(),
        contact_email: form.contact_email.trim() || null,
        contact_phone: form.contact_phone.trim() || null,
        contact_phone_alt: form.contact_phone_alt.trim() || null,
        company_name: form.company_name.trim() || null,
        value: form.value || "0",
        currency: form.currency || "INR",
        probability: Number(form.probability) || 0,
        expected_close_date: form.expected_close_date || null,
        source: (form.source === OTHER_OPTION ? form.source_other.trim() : form.source) || null,
        interest: (form.interest === OTHER_OPTION ? form.interest_other.trim() : form.interest.trim()) || null,
        ...(form.industry === "real_estate" ? {
          property_type: (form.property_type === OTHER_OPTION ? form.property_type_other.trim() : form.property_type) || null,
          budget_min: form.budget_min ? Number(form.budget_min) : null,
          budget_max: form.budget_max ? Number(form.budget_max) : null,
          preferred_location: form.preferred_location.trim() || null,
          possession_preference: form.possession_preference || null
        } : {})
      });
      toast.success("Lead created", form.title.trim());
      setFormOpen(false);
    } catch (submitError) {
      setFormError(extractErrorMessage(submitError));
    } finally {
      setSubmitting(false);
    }
  }

  // --- Stage transition modal -------------------------------------------
  const [transitionLeadState, setTransitionLeadState] = useState<Lead | null>(null);
  const [transitionTarget, setTransitionTarget] = useState<PipelineStage | null>(null);
  const [transitionOpen, setTransitionOpen] = useState(false);

  function openTransition(lead: Lead, target: PipelineStage) {
    if (target.code === lead.stage_code) return;
    setTransitionLeadState(lead);
    setTransitionTarget(target);
    setTransitionOpen(true);
  }

  // --- CSV import -------------------------------------------------------
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const [importing, setImporting] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  // Default to skipping duplicates so a re-uploaded sheet only adds fresh leads.
  const [skipDuplicates, setSkipDuplicates] = useState(true);
  const [importResult, setImportResult] = useState<LeadImportResult | null>(null);

  function openImportDialog() {
    setSkipDuplicates(true);
    setImportOpen(true);
  }

  async function handleImportFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Reset the input so picking the same file twice still triggers onChange.
    event.target.value = "";
    if (!file) return;
    setImporting(true);
    try {
      const result = await leadsService.importCsv(file, skipDuplicates);
      setImportOpen(false);
      setImportResult(result);
      const dupNote = skipDuplicates
        ? (result.skipped > 0 ? `, ${result.skipped} duplicate${result.skipped === 1 ? "" : "s"} skipped` : "")
        : (result.duplicates.length > 0 ? `, ${result.duplicates.length} duplicate${result.duplicates.length === 1 ? "" : "s"} flagged` : "");
      toast.success(
        "Import done",
        `${result.created} lead${result.created === 1 ? "" : "s"} created` +
          (result.promoted > 0 ? `, ${result.promoted} promoted to customer` : "") +
          dupNote +
          (result.errors.length > 0 ? `, ${result.errors.length} row error${result.errors.length === 1 ? "" : "s"}` : "")
      );
      await refresh();
    } catch (err) {
      toast.error("Import failed", extractErrorMessage(err));
    } finally {
      setImporting(false);
    }
  }

  // --- Drawer ------------------------------------------------------------
  const [drawerLead, setDrawerLead] = useState<Lead | null>(null);
  const [drawerKey, setDrawerKey] = useState(0);

  useEffect(() => {
    if (!drawerLead) return;
    const refreshed = leads.find((lead) => lead.id === drawerLead.id);
    if (refreshed && refreshed !== drawerLead) {
      setDrawerLead(refreshed);
    }
  }, [leads, drawerLead]);

  // --- List columns (spec §3.1) ------------------------------------------
  const columns: DataTableColumn<Lead>[] = [
    ...(canAssign
      ? [{
          key: "select",
          width: "36px",
          header: (
            <input
              type="checkbox"
              checked={allPageSelected}
              onChange={toggleSelectAllOnPage}
              aria-label="Select all on page"
            />
          ),
          render: (lead: Lead) => (
            <input
              type="checkbox"
              checked={selectedIds.has(lead.id)}
              onChange={() => toggleSelect(lead.id)}
              aria-label="Select lead"
            />
          ),
        } as DataTableColumn<Lead>]
      : []),
    {
      key: "lead",
      header: "Lead",
      width: "15%",
      render: (lead) => (
        <button type="button" className="link" onClick={() => setDrawerLead(lead)} style={{ textAlign: "left", maxWidth: "100%" }}>
          <div style={{ fontWeight: 600, display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
            {lead.is_duplicate && <DuplicateMark />}
            <span className="cell-truncate">{lead.contact_name || lead.customer?.contact_name || lead.title}</span>
          </div>
          <div className="muted text-xs cell-truncate">{lead.title}</div>
        </button>
      )
    },
    {
      key: "lead_number",
      header: "Lead #",
      width: "6%",
      render: (lead) => <span className="muted">{lead.lead_number}</span>
    },
    {
      key: "email",
      header: "Email",
      width: "16%",
      render: (lead) => (
        <span className="text-sm cell-truncate" title={lead.contact_email ?? lead.customer?.email ?? ""}>
          {lead.contact_email ?? lead.customer?.email ?? "—"}
        </span>
      )
    },
    {
      key: "stage",
      header: "Stage",
      width: "18%",
      render: (lead) => {
        const stage = getStage(lead.industry, lead.stage_code);
        const tone = stage ? pipelineCategoryTone(stage.category) : "neutral";
        const industryStages = byIndustry[lead.industry] ?? [];
        // Read-only badge for users without LEAD_MANAGE so they see the stage
        // but can't trigger a transition.
        if (!canManage) {
          return (
            <Badge tone={tone}>
              {stage ? `${stage.position}. ${stage.name}` : lead.stage_code}
            </Badge>
          );
        }
        return (
          <select
            className={`stage-select stage-select--${tone}`}
            value={lead.stage_code}
            onChange={(event) => {
              const target = industryStages.find((s) => s.code === event.target.value);
              if (target && target.code !== lead.stage_code) {
                openTransition(lead, target);
              }
            }}
            onClick={(event) => event.stopPropagation()}
            title="Move to a different stage — opens the comment box"
            aria-label={`Stage for lead ${lead.lead_number}`}
          >
            {industryStages.map((s) => (
              <option key={s.id} value={s.code}>
                {s.position}. {s.name}
              </option>
            ))}
          </select>
        );
      }
    },
    {
      key: "source",
      header: "Source",
      width: "9%",
      render: (lead) => <span className="cell-truncate" title={lead.source ?? ""}>{lead.source ?? "—"}</span>
    },
    {
      key: "interest",
      header: industryInterestLabel((industryFilter || user?.business_type || "education") as LeadIndustry),
      width: "12%",
      render: (lead) => (
        <span className="cell-truncate" title={lead.interest ?? ""}>{lead.interest ?? "—"}</span>
      )
    },
    {
      key: "owner",
      header: "Owner",
      width: "13%",
      render: (lead) =>
        canAssign ? (
          <select
            className="stage-select stage-select--neutral"
            value={lead.assigned_to_id ?? ""}
            onClick={(event) => event.stopPropagation()}
            onChange={(event) => void handleAssign(lead, event.target.value || null)}
            aria-label={`Owner for lead ${lead.lead_number}`}
            title="Assign this lead to a user"
          >
            <option value="">Unassigned</option>
            {assignableUsers.map((u) => (
              <option key={u.id} value={u.id}>
                {u.first_name} {u.last_name}
              </option>
            ))}
          </select>
        ) : lead.assigned_to ? (
          `${lead.assigned_to.first_name} ${lead.assigned_to.last_name}`
        ) : (
          <span className="muted">Unassigned</span>
        )
    },
    {
      key: "value",
      header: "Value / Budget",
      align: "right",
      width: "12%",
      render: (lead) => {
        // Real estate has no single Value — show the Budget min–max range,
        // stacked (min over max) so it never clips in a narrow column.
        if (lead.industry === "real_estate") {
          const cur = lead.currency || "INR";
          const min = lead.budget_min != null ? formatCurrency(lead.budget_min, cur) : null;
          const max = lead.budget_max != null ? formatCurrency(lead.budget_max, cur) : null;
          if (!min && !max) return <span className="muted">—</span>;
          return (
            <span className="cell-nowrap" style={{ lineHeight: 1.3 }}>
              {min ?? "—"}
              <br />
              <span className="muted">{max ?? "—"}</span>
            </span>
          );
        }
        return <span className="cell-nowrap">{formatCurrency(lead.value, lead.currency || "INR")}</span>;
      }
    }
  ];

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Leads Management</h1>
          <p>Industry-aware pipeline with mandatory comments on every stage move.</p>
        </div>
        <div className="page-header__actions">
          <div className="view-toggle" role="tablist">
            <button
              className={view === "list" ? "is-active" : ""}
              onClick={() => setView("list")}
              type="button"
              role="tab"
              aria-selected={view === "list"}
            >
              <ListIcon size={14} style={{ verticalAlign: "middle", marginRight: 4 }} /> List
            </button>
            <button
              className={view === "kanban" ? "is-active" : ""}
              onClick={() => setView("kanban")}
              type="button"
              role="tab"
              aria-selected={view === "kanban"}
            >
              <LayoutGrid size={14} style={{ verticalAlign: "middle", marginRight: 4 }} /> Kanban
            </button>
          </div>
          <Button variant="secondary" size="sm" icon={<RefreshCw size={14} />} onClick={() => void refresh()} loading={loading}>
            Refresh
          </Button>
          {canExport && (
            <Button
              variant="secondary"
              size="sm"
              icon={<Download size={14} />}
              onClick={() => {
                void exportsService
                  .leads()
                  .catch((e) => toast.error("Export failed", extractErrorMessage(e)));
              }}
              title="Download all leads as a CSV (matches your business type's columns)"
            >
              Export
            </Button>
          )}
          {canImport && (
            <>
              <Button
                variant="secondary"
                size="sm"
                icon={<Download size={14} />}
                onClick={() => {
                  void leadsService
                    .downloadImportTemplate()
                    .catch((err) => toast.error("Template download failed", extractErrorMessage(err)));
                }}
                title="Download a starter CSV template you can fill in and upload"
              >
                Template
              </Button>
              <Button
                variant="secondary"
                size="sm"
                icon={<Upload size={14} />}
                onClick={openImportDialog}
                loading={importing}
              >
                Upload CSV
              </Button>
              <input
                ref={importInputRef}
                type="file"
                accept=".csv,text/csv"
                style={{ display: "none" }}
                onChange={(event) => void handleImportFile(event)}
              />
            </>
          )}
          {canManage && (
            <Button icon={<Plus size={14} />} onClick={openCreate}>
              New lead
            </Button>
          )}
        </div>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="row" style={{ gap: "0.75rem", padding: "1rem 1.25rem", borderBottom: "1px solid var(--color-border)", flexWrap: "wrap" }}>
          {user?.business_type ? (
            // Single-vertical orgs (the default since Phase 7) — the industry
            // is implicit. Show it as a read-only chip instead of a dropdown
            // that would offer the other vertical we can never load data for.
            <div
              className="muted text-sm"
              style={{ display: "flex", alignItems: "center", padding: "0 0.5rem" }}
              title="Your account is scoped to this industry"
            >
              Industry: <strong style={{ marginLeft: 4 }}>{titleCase(user.business_type)}</strong>
            </div>
          ) : (
            <select
              className="select"
              value={industryFilter}
              onChange={(event) => {
                setIndustryFilter((event.target.value || "") as LeadIndustry | "");
                setStageFilter("");
                setPage(1);
              }}
              aria-label="Filter by industry"
            >
              <option value="">All industries</option>
              {leadIndustryOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          )}
          <select
            className="select"
            value={stageFilter}
            onChange={(event) => {
              setStageFilter(event.target.value);
              setPage(1);
            }}
            aria-label="Filter by stage"
            style={{ minWidth: 220 }}
          >
            <option value="">All stages</option>
            {stageOptionsForFilter.map((option) => (
              <option key={`${option.value}-${option.label}`} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {view === "list" ? (
          <>
            {canAssign && selectedIds.size > 0 && (
              <div
                className="row"
                style={{
                  gap: "0.75rem",
                  alignItems: "center",
                  padding: "0.55rem 0.8rem",
                  background: "var(--color-surface-muted)",
                  borderRadius: "var(--radius-md)",
                  marginBottom: "0.5rem",
                  flexWrap: "wrap",
                }}
              >
                <strong>{selectedIds.size} selected</strong>
                <select
                  className="select"
                  value={bulkOwner}
                  onChange={(e) => setBulkOwner(e.target.value)}
                  style={{ maxWidth: 240 }}
                  aria-label="Change owner to"
                >
                  <option value="">Change owner to…</option>
                  {assignableUsers.map((u) => (
                    <option key={u.id} value={u.id}>{u.first_name} {u.last_name}</option>
                  ))}
                </select>
                <Button size="sm" loading={bulkReassigning} disabled={!bulkOwner} onClick={() => void handleBulkReassign()}>
                  Change Owner
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setSelectedIds(new Set())}>Clear</Button>
              </div>
            )}
            <div className="table-wrap table-wrap--leads" style={{ border: "none", borderRadius: 0, boxShadow: "none" }}>
              {loading && leads.length === 0 ? (
                <LoadingBlock label="Loading leads…" />
              ) : (
                <DataTable
                  columns={columns}
                  rows={leads}
                  rowKey={(lead) => lead.id}
                  empty={<EmptyState title="No leads yet" description="Create your first lead to start tracking deals." />}
                />
              )}
            </div>
            <Pagination
              page={pagination.page}
              pageSize={pagination.page_size}
              total={pagination.total}
              totalPages={pagination.total_pages}
              onPageChange={setPage}
            />
          </>
        ) : (
          <KanbanView
            leads={leads}
            industryFilter={industryFilter}
            onCardClick={(lead) => setDrawerLead(lead)}
            onStageDrop={(lead, target) => openTransition(lead, target)}
          />
        )}
      </div>

      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title="New lead"
        footer={
          <>
            <Button variant="secondary" onClick={() => setFormOpen(false)} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" form="lead-form" loading={submitting} disabled={submitting}>
              {duplicates.length > 0 ? "Create anyway" : "Create lead"}
            </Button>
          </>
        }
      >
        <form id="lead-form" className="form" onSubmit={handleCreateSubmit}>
          {user?.business_type ? (
            <div className="muted text-sm" style={{ marginBottom: "0.25rem" }}>
              Industry: <strong>{titleCase(user.business_type)}</strong>{" "}
              <span className="text-xs">(inherited from your account)</span>
            </div>
          ) : (
            <SelectField
              id="lead-industry"
              label="Industry"
              value={form.industry}
              onChange={(event) => setForm({ ...form, industry: event.target.value as LeadIndustry })}
              options={leadIndustryOptions}
              hint="Your account has no business type set — pick one for this lead."
            />
          )}
          <TextField
            id="lead-title"
            label="Title"
            value={form.title}
            onChange={(event) => setForm({ ...form, title: event.target.value })}
            required
            placeholder="Short headline e.g. 'MBA Marketing applicant'"
          />
          <TextField
            id="lead-contact-name"
            label="Contact name"
            value={form.contact_name}
            onChange={(event) => setForm({ ...form, contact_name: event.target.value })}
            required
            hint="Becomes the Customer's contact name on Sold."
          />
          <div className="form-grid">
            <TextField
              id="lead-contact-email"
              label="Email"
              type="email"
              value={form.contact_email}
              onChange={(event) => { setForm({ ...form, contact_email: event.target.value }); resetDupCheck(); }}
              required
              placeholder="name@example.com"
            />
            <TextField
              id="lead-contact-phone"
              label="Phone"
              value={form.contact_phone}
              onChange={(event) => { setForm({ ...form, contact_phone: event.target.value }); resetDupCheck(); }}
              required
              placeholder="+91 99876 54321"
            />
          </div>
          <TextField
            id="lead-contact-phone-alt"
            label="Alternate phone"
            value={form.contact_phone_alt}
            onChange={(event) => setForm({ ...form, contact_phone_alt: event.target.value })}
            placeholder="Optional — a second number to reach this contact"
          />
          {duplicates.length > 0 && (
            <div className="notice-banner" role="status">
              <strong>Possible duplicate{duplicates.length > 1 ? "s" : ""}.</strong> A lead with this
              email or phone already exists in your workspace:
              <ul style={{ margin: "0.4rem 0 0.25rem", paddingLeft: "1.1rem" }}>
                {duplicates.map((dup) => (
                  <li key={dup.id}>
                    <button type="button" className="link" onClick={() => openExistingLead(dup)} style={{ textAlign: "left" }}>
                      #{dup.lead_number} — {dup.contact_name}
                    </button>
                    {(dup.contact_email || dup.contact_phone) && (
                      <span className="muted text-xs">
                        {" "}· {[dup.contact_email, dup.contact_phone].filter(Boolean).join(" · ")}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
              Click <strong>Create anyway</strong> below to add it regardless.
            </div>
          )}
          <TextField
            id="lead-company"
            label="Company / Organization"
            value={form.company_name}
            onChange={(event) => setForm({ ...form, company_name: event.target.value })}
            placeholder="Optional"
          />
          {form.industry === "real_estate" ? (
            <>
              <SelectField
                id="lead-interest"
                label={`${industryInterestLabel(form.industry)} *`}
                value={form.interest}
                onChange={(event) => setForm({ ...form, interest: event.target.value })}
                required
                options={[{ value: "", label: "Select…" }, ...propertyInterestOptions]}
              />
              {form.interest === OTHER_OPTION && (
                <TextField
                  id="lead-interest-other"
                  label="Please specify property interest"
                  value={form.interest_other}
                  onChange={(event) => setForm({ ...form, interest_other: event.target.value })}
                  required
                />
              )}
            </>
          ) : (
            <TextField
              id="lead-interest"
              label={industryInterestLabel(form.industry)}
              value={form.interest}
              onChange={(event) => setForm({ ...form, interest: event.target.value })}
              placeholder={form.industry === "travel" ? "e.g. Bali — 7 days" : "e.g. MBA — Marketing"}
            />
          )}
          {form.industry === "real_estate" && (
            <>
              <SelectField
                id="lead-property-type"
                label="Property type"
                value={form.property_type}
                onChange={(event) => setForm({ ...form, property_type: event.target.value })}
                options={[
                  { value: "apartment", label: "Apartment" },
                  { value: "villa", label: "Villa / Independent house" },
                  { value: "plot", label: "Plot / Land" },
                  { value: "commercial", label: "Commercial" },
                  { value: OTHER_OPTION, label: "Other…" }
                ]}
              />
              {form.property_type === OTHER_OPTION && (
                <TextField
                  id="lead-property-type-other"
                  label="Please specify property type"
                  value={form.property_type_other}
                  onChange={(event) => setForm({ ...form, property_type_other: event.target.value })}
                />
              )}
              <div className="form-grid">
                <TextField
                  id="lead-budget-min"
                  label="Budget min (₹)"
                  type="number"
                  min={0}
                  step="100000"
                  value={form.budget_min}
                  onChange={(event) => setForm({ ...form, budget_min: event.target.value })}
                  placeholder="e.g. 5000000"
                />
                <TextField
                  id="lead-budget-max"
                  label="Budget max (₹)"
                  type="number"
                  min={0}
                  step="100000"
                  value={form.budget_max}
                  onChange={(event) => setForm({ ...form, budget_max: event.target.value })}
                  placeholder="e.g. 10000000"
                />
              </div>
              <TextField
                id="lead-preferred-location"
                label="Preferred location"
                value={form.preferred_location}
                onChange={(event) => setForm({ ...form, preferred_location: event.target.value })}
                placeholder="e.g. Whitefield, Bengaluru"
              />
              <SelectField
                id="lead-possession-preference"
                label="Possession preference"
                value={form.possession_preference}
                onChange={(event) => setForm({ ...form, possession_preference: event.target.value })}
                options={[
                  { value: "immediate", label: "Immediate / Ready to move" },
                  { value: "within_6_months", label: "Within 6 months" },
                  { value: "1_year", label: "Within 1 year" },
                  { value: "2_years", label: "Within 2 years" }
                ]}
              />
            </>
          )}
          <SelectField
            id="lead-source"
            label="Source *"
            value={form.source}
            onChange={(event) => setForm({ ...form, source: event.target.value })}
            required
            options={[{ value: "", label: "Select…" }, ...leadSourceOptions]}
          />
          {form.source === OTHER_OPTION && (
            <TextField
              id="lead-source-other"
              label="Please specify source"
              value={form.source_other}
              onChange={(event) => setForm({ ...form, source_other: event.target.value })}
              required
            />
          )}
          {/* Real estate captures a Budget min–max range (above) instead of a
              single Value, so Value/Currency are hidden for that vertical. */}
          {form.industry !== "real_estate" && (
            <div className="form-grid">
              <TextField
                id="lead-value"
                label="Value"
                type="number"
                min={0}
                step="0.01"
                value={form.value}
                onChange={(event) => setForm({ ...form, value: event.target.value })}
              />
              <SelectField
                id="lead-currency"
                label="Currency"
                value={form.currency}
                onChange={(event) => setForm({ ...form, currency: event.target.value })}
                options={allowedCurrencies.map((code) => ({ value: code, label: code }))}
                hint={
                  allowedCurrencies.length > 1
                    ? `Available for your account: ${allowedCurrencies.join(" / ")}`
                    : undefined
                }
              />
            </div>
          )}
          <TextField
            id="lead-close-date"
            label="Expected close"
            type="date"
            value={form.expected_close_date}
            onChange={(event) => setForm({ ...form, expected_close_date: event.target.value })}
          />
          {formError && <div className="error-banner">{formError}</div>}
        </form>
      </Modal>

      <StageTransitionModal
        open={transitionOpen}
        lead={transitionLeadState}
        targetStage={transitionTarget}
        onClose={() => setTransitionOpen(false)}
        onSubmit={async (payload) => {
          if (!transitionLeadState) return;
          const { site_visit, ...transitionPayload } = payload;
          await transitionLead(transitionLeadState.id, transitionPayload);
          // When moving to the Site Visit stage, book the visit on the calendar.
          if (site_visit) {
            try {
              await siteVisitsService.create({
                leadId: transitionLeadState.id,
                projectId: site_visit.project_id,
                scheduledAt: site_visit.scheduled_at,
              });
            } catch (err) {
              toast.error("Site visit not booked", extractErrorMessage(err));
            }
          }
          toast.success(
            "Stage updated",
            site_visit
              ? "Moved · site visit booked on the calendar"
              : `Moved to ${transitionTarget?.name ?? payload.to_stage_code}`
          );
          setDrawerKey((k) => k + 1);
        }}
      />

      <LeadDrawer
        open={Boolean(drawerLead)}
        lead={drawerLead}
        onClose={() => setDrawerLead(null)}
        onTransitionRequest={(lead, target) => openTransition(lead, target)}
        refreshKey={drawerKey}
      />

      {/* Upload CSV — pick skip-duplicates before choosing the file. */}
      <Modal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        title="Import leads from CSV"
        footer={
          <>
            <Button variant="secondary" onClick={() => setImportOpen(false)}>
              Cancel
            </Button>
            <Button
              icon={<Upload size={14} />}
              loading={importing}
              onClick={() => importInputRef.current?.click()}
            >
              Choose CSV file
            </Button>
          </>
        }
      >
        <div className="stack">
          <p className="muted text-sm">
            Upload a CSV matching your business type — use the <strong>Template</strong> button for the
            correct columns. Email and phone are required; rows missing them are reported as errors.
          </p>
          <label style={{ display: "flex", gap: 8, alignItems: "flex-start", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={skipDuplicates}
              onChange={(event) => setSkipDuplicates(event.target.checked)}
              style={{ marginTop: 3 }}
            />
            <span>
              <strong>Skip duplicate leads</strong> — only import fresh leads (rows whose email or
              phone already matches an existing lead are skipped).
              <br />
              <span className="muted text-xs">
                Uncheck to import all rows; duplicates are still created and flagged with a red “!”.
              </span>
            </span>
          </label>
        </div>
      </Modal>

      {/* CSV import result — surfaced when there are duplicates or row errors.
          A clean import is summarised by the toast and the refreshed list. */}
      <Modal
        open={Boolean(importResult && (importResult.errors.length > 0 || importResult.duplicates.length > 0))}
        onClose={() => setImportResult(null)}
        title="Import summary"
        footer={
          <Button onClick={() => setImportResult(null)}>
            Close
          </Button>
        }
      >
        {importResult && (
          <div className="stack">
            <div>
              <strong>{importResult.created}</strong> lead
              {importResult.created === 1 ? "" : "s"} created
              {importResult.promoted > 0 && (
                <> · <strong>{importResult.promoted}</strong> auto-promoted to customer</>
              )}
              {importResult.skipped > 0 && (
                <> · <strong>{importResult.skipped}</strong> duplicate{importResult.skipped === 1 ? "" : "s"} skipped</>
              )}
              {importResult.errors.length > 0 && (
                <> · <strong>{importResult.errors.length}</strong> row error{importResult.errors.length === 1 ? "" : "s"}</>
              )}
            </div>

            {importResult.duplicates.length > 0 && (
              <>
                <div className="muted text-sm">
                  {importResult.duplicates.some((d) => d.skipped)
                    ? "These rows matched an existing lead and were skipped:"
                    : "These rows matched an existing lead and were imported (flagged with a red “!”):"}
                </div>
                <table className="table">
                  <thead>
                    <tr>
                      <th style={{ width: 56, textAlign: "left" }}>Row</th>
                      <th style={{ textAlign: "left" }}>Contact</th>
                      <th style={{ textAlign: "left" }}>Matches</th>
                      <th style={{ width: 90, textAlign: "left" }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {importResult.duplicates.map((d) => (
                      <tr key={`dup-${d.row}`}>
                        <td>{d.row}</td>
                        <td>
                          {d.contact_name ?? "—"}
                          {(d.contact_email || d.contact_phone) && (
                            <div className="muted text-xs">
                              {[d.contact_email, d.contact_phone].filter(Boolean).join(" · ")}
                            </div>
                          )}
                        </td>
                        <td>{d.matched}</td>
                        <td>{d.skipped ? "Skipped" : "Imported"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}

            {importResult.errors.length > 0 && (
              <>
                <div className="muted text-sm">
                  Fix these rows in your sheet and re-upload — already-created leads aren't duplicated.
                </div>
                <table className="table">
                  <thead>
                    <tr>
                      <th style={{ width: 56, textAlign: "left" }}>Row</th>
                      <th style={{ textAlign: "left" }}>Error</th>
                    </tr>
                  </thead>
                  <tbody>
                    {importResult.errors.map((err) => (
                      <tr key={`err-${err.row}`}>
                        <td>{err.row}</td>
                        <td>{err.error}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        )}
      </Modal>
    </>
  );
}


// --- Kanban view ----------------------------------------------------------

interface KanbanViewProps {
  leads: Lead[];
  industryFilter: LeadIndustry | "";
  onCardClick: (lead: Lead) => void;
  onStageDrop: (lead: Lead, target: PipelineStage) => void;
}


function KanbanView({ leads, industryFilter, onCardClick, onStageDrop }: KanbanViewProps) {
  const { byIndustry, getStage } = usePipelines();

  // Kanban can only show one industry at a time — pick the user's filter,
  // otherwise default to the industry of the first visible lead.
  const industry: LeadIndustry =
    industryFilter || leads[0]?.industry || "education";
  const stages = byIndustry[industry];

  const leadsByStage = useMemo(() => {
    const map = new Map<string, Lead[]>();
    for (const stage of stages) map.set(stage.code, []);
    for (const lead of leads) {
      if (lead.industry !== industry) continue;
      const bucket = map.get(lead.stage_code);
      if (bucket) bucket.push(lead);
    }
    return map;
  }, [leads, stages, industry]);

  const [dragOver, setDragOver] = useState<string | null>(null);

  function handleDragStart(event: DragEvent<HTMLDivElement>, lead: Lead) {
    event.dataTransfer.setData("application/x-lead-id", lead.id);
    event.dataTransfer.effectAllowed = "move";
  }

  function handleDrop(event: DragEvent<HTMLDivElement>, stage: PipelineStage) {
    event.preventDefault();
    setDragOver(null);
    const leadId = event.dataTransfer.getData("application/x-lead-id");
    const lead = leads.find((l) => l.id === leadId);
    if (lead && lead.stage_code !== stage.code) {
      onStageDrop(lead, stage);
    }
  }

  if (!industryFilter && leads.some((lead) => lead.industry !== industry)) {
    return (
      <div style={{ padding: "1rem" }}>
        <div className="muted text-sm" style={{ marginBottom: "0.5rem" }}>
          Kanban shows one industry at a time — currently <strong>{titleCase(industry)}</strong>. Use the
          industry filter to switch.
        </div>
      </div>
    );
  }

  return (
    <div className="kanban">
      {stages.map((stage) => {
        const bucket = leadsByStage.get(stage.code) ?? [];
        return (
          <div
            key={stage.id}
            className={`kanban__column ${dragOver === stage.code ? "kanban__card--drag-over" : ""}`}
            onDragOver={(event) => {
              event.preventDefault();
              setDragOver(stage.code);
            }}
            onDragLeave={() => setDragOver((current) => (current === stage.code ? null : current))}
            onDrop={(event) => handleDrop(event, stage)}
          >
            <div className="kanban__column-header">
              <span>
                {stage.position}. {stage.name}
              </span>
              <Badge tone={pipelineCategoryTone(stage.category)}>{bucket.length}</Badge>
            </div>
            {bucket.map((lead) => {
              const currentStage = getStage(lead.industry, lead.stage_code);
              return (
                <div
                  key={lead.id}
                  className="kanban__card"
                  draggable
                  onDragStart={(event) => handleDragStart(event, lead)}
                  onClick={() => onCardClick(lead)}
                >
                  <div className="kanban__card-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    {lead.is_duplicate && <DuplicateMark />}
                    <span>{lead.title}</span>
                  </div>
                  <div className="kanban__card-meta">
                    #{lead.lead_number} · {lead.customer?.company_name ?? "—"}
                  </div>
                  {currentStage && (
                    <div className="kanban__card-meta">
                      {formatCurrency(lead.value)} · {lead.probability}%
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
