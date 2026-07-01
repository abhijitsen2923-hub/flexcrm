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
import { leadsService, type LeadDuplicate, type LeadImportResult } from "../services/leads";
import { organizationsService } from "../services/organizations";
import type { Lead, LeadIndustry, Organization, PipelineStage } from "../types";
import { extractErrorMessage } from "../utils/errors";
import { formatCurrency, formatRelative } from "../utils/format";
import { industryInterestLabel, leadIndustryOptions, pipelineCategoryTone, titleCase } from "../utils/options";


type ViewMode = "list" | "kanban";


interface CreateFormState {
  industry: LeadIndustry;
  title: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  company_name: string;
  value: string;
  currency: string;
  probability: string;
  expected_close_date: string;
  source: string;
  interest: string;
  // Real-estate specific (only submitted when industry === "real_estate")
  property_type: string;
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
    company_name: "",
    value: "0",
    currency: defaultCurrency,
    probability: "0",
    expected_close_date: "",
    source: "",
    interest: "",
    property_type: "",
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
        company_name: form.company_name.trim() || null,
        value: form.value || "0",
        currency: form.currency || "INR",
        probability: Number(form.probability) || 0,
        expected_close_date: form.expected_close_date || null,
        source: form.source.trim() || null,
        interest: form.interest.trim() || null,
        ...(form.industry === "real_estate" ? {
          property_type: form.property_type || null,
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
  const [importResult, setImportResult] = useState<LeadImportResult | null>(null);

  function openImportPicker() {
    importInputRef.current?.click();
  }

  async function handleImportFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Reset the input so picking the same file twice still triggers onChange.
    event.target.value = "";
    if (!file) return;
    setImporting(true);
    try {
      const result = await leadsService.importCsv(file);
      setImportResult(result);
      toast.success(
        "Import done",
        `${result.created} lead${result.created === 1 ? "" : "s"} created` +
          (result.promoted > 0 ? `, ${result.promoted} promoted to customer` : "") +
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
    {
      key: "lead",
      header: "Lead",
      render: (lead) => (
        <button type="button" className="link" onClick={() => setDrawerLead(lead)} style={{ textAlign: "left" }}>
          <div style={{ fontWeight: 600 }}>{lead.contact_name || lead.customer?.contact_name || lead.title}</div>
          <div className="muted text-xs">{lead.title}</div>
        </button>
      )
    },
    {
      key: "lead_number",
      header: "Lead #",
      render: (lead) => <span className="muted">{lead.lead_number}</span>
    },
    {
      key: "email",
      header: "Email",
      render: (lead) => (
        <span className="text-sm">{lead.contact_email ?? lead.customer?.email ?? "—"}</span>
      )
    },
    {
      key: "stage",
      header: "Stage",
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
      render: (lead) => lead.source ?? "—"
    },
    {
      key: "interest",
      header: "Course / Destination",
      render: (lead) => (
        <span title={lead.interest ?? ""}>
          <span className="muted text-xs">{industryInterestLabel(lead.industry)}: </span>
          {lead.interest ?? "—"}
        </span>
      )
    },
    {
      key: "owner",
      header: "Owner",
      render: (lead) =>
        lead.assigned_to ? `${lead.assigned_to.first_name} ${lead.assigned_to.last_name}` : <span className="muted">Unassigned</span>
    },
    {
      key: "last_comment",
      header: "Last Comment",
      render: (lead) =>
        lead.last_comment_preview ? (
          <span title={lead.last_comment_preview} className="text-truncate">
            {lead.last_comment_preview}
            <span className="muted text-xs"> · {formatRelative(lead.last_comment_at)}</span>
          </span>
        ) : (
          <span className="muted">—</span>
        )
    },
    {
      key: "value",
      header: "Value",
      align: "right",
      render: (lead) => formatCurrency(lead.value, lead.currency || "INR")
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
          {canImport && (
            <>
              <Button
                variant="secondary"
                size="sm"
                icon={<Download size={14} />}
                onClick={() => window.open("/api/v1/leads/import/template.csv", "_blank")}
                title="Download a starter CSV template you can fill in and upload"
              >
                Template
              </Button>
              <Button
                variant="secondary"
                size="sm"
                icon={<Upload size={14} />}
                onClick={openImportPicker}
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
            <div className="table-wrap" style={{ border: "none", borderRadius: 0, boxShadow: "none" }}>
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
              placeholder="Optional"
            />
            <TextField
              id="lead-contact-phone"
              label="Phone"
              value={form.contact_phone}
              onChange={(event) => { setForm({ ...form, contact_phone: event.target.value }); resetDupCheck(); }}
              placeholder="Optional"
            />
          </div>
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
          <TextField
            id="lead-interest"
            label={industryInterestLabel(form.industry)}
            value={form.interest}
            onChange={(event) => setForm({ ...form, interest: event.target.value })}
            placeholder={
              form.industry === "travel"
                ? "e.g. Bali — 7 days"
                : form.industry === "real_estate"
                  ? "e.g. 2BHK in North Bengaluru"
                  : "e.g. MBA — Marketing"
            }
          />
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
                  { value: "commercial", label: "Commercial" }
                ]}
              />
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
          <TextField
            id="lead-source"
            label="Source"
            value={form.source}
            onChange={(event) => setForm({ ...form, source: event.target.value })}
            placeholder="Instagram, Referral, Walk-in…"
          />
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
          <div className="form-grid">
            <TextField
              id="lead-probability"
              label="Probability (%)"
              type="number"
              min={0}
              max={100}
              value={form.probability}
              onChange={(event) => setForm({ ...form, probability: event.target.value })}
            />
            <TextField
              id="lead-close-date"
              label="Expected close"
              type="date"
              value={form.expected_close_date}
              onChange={(event) => setForm({ ...form, expected_close_date: event.target.value })}
            />
          </div>
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
          await transitionLead(transitionLeadState.id, payload);
          toast.success(
            "Stage updated",
            `Moved to ${transitionTarget?.name ?? payload.to_stage_code}`
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

      {/* CSV import result — only surface the modal when there are row-level
          errors. A clean import is summarised by the toast and the refreshed
          list; no modal needed. */}
      <Modal
        open={Boolean(importResult && importResult.errors.length > 0)}
        onClose={() => setImportResult(null)}
        title="Import finished with row errors"
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
              )}{" "}
              · <strong>{importResult.errors.length}</strong> skipped.
            </div>
            <div className="muted text-sm">
              Fix the rows below in your sheet and re-upload — already-created leads aren't duplicated.
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: 80, textAlign: "left" }}>Row</th>
                  <th style={{ textAlign: "left" }}>Error</th>
                </tr>
              </thead>
              <tbody>
                {importResult.errors.map((err) => (
                  <tr key={err.row}>
                    <td>{err.row}</td>
                    <td>{err.error}</td>
                  </tr>
                ))}
              </tbody>
            </table>
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
                  <div className="kanban__card-title">{lead.title}</div>
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
