import { useEffect, useRef, useState, type FormEvent } from "react";
import { Archive, Building2, Download, Image, Pencil, Plus, Trash2, Upload } from "lucide-react";
import { Button, Card, ConfirmDialog, DataTable, EmptyState, Modal, SelectField, TextField, useToast } from "../../components";
import type { DataTableColumn } from "../../components";
import { useInventory } from "../../hooks/useInventory";
import { usePermissions } from "../../hooks/usePermissions";
import { inventoryService } from "../../services/inventory";
import { exportsService } from "../../services/exports";
import type { GarageOption, Project, ProjectMedia, ProjectPossessionRollup, Tower, Unit, UnitType } from "../../types/realestate";
import { LoadingBlock } from "../../components/ui/Spinner";
import { extractErrorMessage } from "../../utils/errors";
import { formatInr } from "../../utils/format";
import {
  EMPTY_PARKING_COUNTS,
  applyRates,
  cardPayload,
  describeCreated,
  initialCards,
  initialParkingCounts,
  isParkingBlock,
  parkingCountsByType,
  parkingPayload,
  parkingTotal,
  plannedAdds,
  plannedParkingAdds,
  syncCardsWithDetails,
  totalOf,
  validateLayout,
  type LayoutDetails,
  type ParkingCountsForm,
  type ProjectRates,
  type TowerCard,
} from "../../utils/projectInventory";
import { ProjectInventoryEditor } from "./components/ProjectInventoryEditor";
import "./ProjectsPage.css";

const UNIT_TYPE_OPTIONS: { value: UnitType; label: string }[] = [
  { value: "residential", label: "Residential / Flat" },
  { value: "parking", label: "Parking" },
  { value: "shop", label: "Shop / Commercial" },
  { value: "godown", label: "Godown / Warehouse" },
];

interface ProjectFormState {
  name: string;
  builder_name: string;
  location: string;
  city: string;
  rera_number: string;
  // Project detail (Phase B) — numeric fields kept as strings for the inputs.
  pin_code: string;
  landmark: string;
  total_towers: string;
  total_floors: string;
  flats_per_floor: string;
  // Default box-price components.
  rate_a: string;
  rate_b: string;
  rate_c: string;
  parking_cost: string;
  legal_fees: string;
  overhead_cost: string;
  other_charges: string;
  sinking_fund: string;
  amenities_charges: string;
}

const EMPTY_PROJECT_FORM: ProjectFormState = {
  name: "",
  builder_name: "",
  location: "",
  city: "",
  rera_number: "",
  pin_code: "",
  landmark: "",
  total_towers: "",
  total_floors: "",
  flats_per_floor: "",
  rate_a: "",
  rate_b: "",
  rate_c: "",
  parking_cost: "",
  legal_fees: "",
  overhead_cost: "",
  other_charges: "",
  sinking_fund: "",
  amenities_charges: "",
};

// Parse a numeric input string → number, or null when blank / invalid.
function numOrNull(s: string): number | null {
  const t = s.trim();
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}
function intOrNull(s: string): number | null {
  const n = numOrNull(s);
  return n === null ? null : Math.trunc(n);
}

// The Towers section follows these details (cards added / laid out as they change) and these rates (suggested
// prices = size × rate).
function detailsOf(form: ProjectFormState): LayoutDetails {
  return { towers: intOrNull(form.total_towers), floors: intOrNull(form.total_floors), flatsPerFloor: intOrNull(form.flats_per_floor) };
}
function ratesOf(form: ProjectFormState): ProjectRates {
  return { rateA: numOrNull(form.rate_a), rateB: numOrNull(form.rate_b), rateC: numOrNull(form.rate_c) };
}

const MEDIA_TYPE_OPTIONS: { value: ProjectMedia["type"]; label: string }[] = [
  { value: "brochure", label: "Brochure" },
  { value: "floor_plan", label: "Floor plan" },
  { value: "image", label: "Image" },
  { value: "video", label: "Video" },
  { value: "virtual_tour", label: "Virtual tour" },
];

function MediaGallery({ project, onChanged }: { project: Project; onChanged: () => Promise<void> | void }) {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [mediaType, setMediaType] = useState<ProjectMedia["type"]>("brochure");
  const [label, setLabel] = useState("");
  const [uploading, setUploading] = useState(false);

  async function upload() {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      toast.error("Choose a file to upload");
      return;
    }
    setUploading(true);
    try {
      await inventoryService.uploadProjectMedia(project.id, file, mediaType, label.trim() || null);
      toast.success("Media uploaded", file.name);
      setLabel("");
      if (fileRef.current) fileRef.current.value = "";
      await onChanged();
    } catch (e) {
      toast.error("Upload failed", extractErrorMessage(e));
    } finally {
      setUploading(false);
    }
  }

  async function remove(id: string) {
    try {
      await inventoryService.deleteProjectMedia(id);
      await onChanged();
    } catch (e) {
      toast.error("Delete failed", extractErrorMessage(e));
    }
  }

  return (
    <div className="stack" style={{ gap: "0.75rem" }}>
      <div className="card" style={{ padding: "0.75rem 1rem" }}>
        <div className="form-grid">
          <SelectField
            id="media-type"
            label="Type"
            value={mediaType}
            onChange={(e) => setMediaType(e.target.value as ProjectMedia["type"])}
            options={MEDIA_TYPE_OPTIONS}
          />
          <TextField
            id="media-label"
            label="Label (optional)"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. 2BHK floor plan"
          />
        </div>
        <div className="row" style={{ gap: "0.75rem", alignItems: "center", marginTop: "0.5rem", flexWrap: "wrap" }}>
          <input ref={fileRef} type="file" accept="image/*,application/pdf,video/*" />
          <Button size="sm" icon={<Upload size={14} />} loading={uploading} onClick={() => void upload()}>
            Upload
          </Button>
        </div>
      </div>

      {project.media.length === 0 ? (
        <p className="media-gallery__empty">No media uploaded yet.</p>
      ) : (
        <div className="media-gallery">
          {project.media.map((m) => (
            <div key={m.id} className="media-gallery__item">
              <a href={m.url} target="_blank" rel="noreferrer" className="media-gallery__link">
                {m.type === "image" ? (
                  <img src={m.url} alt={m.label ?? m.type} className="media-gallery__img" />
                ) : (
                  <div className="media-gallery__doc">
                    <Image size={20} />
                    <span>{m.label ?? m.type}</span>
                  </div>
                )}
              </a>
              <button
                type="button"
                className="media-gallery__delete"
                onClick={() => void remove(m.id)}
                aria-label="Delete media"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const COLUMNS: DataTableColumn<Project>[] = [
  { key: "name", header: "Project", render: (p) => <strong>{p.name}</strong> },
  { key: "builderName", header: "Builder", render: (p) => p.builderName },
  { key: "location", header: "Location", render: (p) => `${p.location}, ${p.city}` },
  { key: "totalUnits", header: "Total Units", render: (p) => p.totalUnits },
  {
    key: "availableUnits",
    header: "Available",
    render: (p) => (
      <span style={{ color: p.availableUnits > 0 ? "var(--status-available)" : "var(--status-sold)", fontWeight: 600 }}>
        {p.availableUnits}
      </span>
    ),
  },
  {
    key: "parking",
    header: "Parking (available / total)",
    render: (p) => (p.totalParking > 0 ? `${p.availableParking} / ${p.totalParking}` : "—"),
  },
  { key: "reraNumber", header: "RERA", render: (p) => p.reraNumber ?? "—" },
];

export default function ProjectsPage() {
  const { projects, loading, refresh } = useInventory();
  const toast = useToast();
  const { has: hasPerm } = usePermissions();
  const canExport = hasPerm("EXPORT_DATA");
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [form, setForm] = useState<ProjectFormState>(EMPTY_PROJECT_FORM);
  const [cards, setCards] = useState<TowerCard[]>([]);
  const [parkingSelected, setParkingSelected] = useState<GarageOption[]>([]);
  const [parkingCounts, setParkingCounts] = useState<ParkingCountsForm>(EMPTY_PARKING_COUNTS);
  const [demandRows, setDemandRows] = useState<{ label: string; percent: string; due_date: string }[]>([]);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Total towers / floors / flats per floor drive the tower cards; the rates drive the suggested prices.
  function setDetail(field: "total_towers" | "total_floors" | "flats_per_floor", value: string) {
    const next = { ...form, [field]: value };
    setForm(next);
    setCards((prev) => syncCardsWithDetails(prev, detailsOf(next), ratesOf(next)));
  }
  function setRate(field: "rate_a" | "rate_b" | "rate_c", value: string) {
    const next = { ...form, [field]: value };
    setForm(next);
    setCards((prev) => applyRates(prev, ratesOf(next)));
  }
  function setDemandRow(i: number, patch: Partial<{ label: string; percent: string; due_date: string }>) {
    setDemandRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }
  const [archiveProject, setArchiveProject] = useState<Project | null>(null);
  const [archiving, setArchiving] = useState(false);

  // Keep the open detail modal in sync with refreshed data (after adding
  // towers/units) — selectedProject is a snapshot; re-point it at the fresh row.
  useEffect(() => {
    if (!selectedProject) return;
    const fresh = projects.find((p) => p.id === selectedProject.id);
    if (fresh && fresh !== selectedProject) setSelectedProject(fresh);
  }, [projects, selectedProject]);

  function openCreate() {
    setEditingProject(null);
    setForm(EMPTY_PROJECT_FORM);
    setCards([]);
    setParkingSelected([]);
    setParkingCounts(EMPTY_PARKING_COUNTS);
    setDemandRows([]);
    setFormError(null);
    setFormOpen(true);
  }

  function openEdit(project: Project) {
    setEditingProject(project);
    const str = (v: number | null) => (v != null ? String(v) : "");
    const next: ProjectFormState = {
      name: project.name,
      builder_name: project.builderName,
      location: project.location,
      city: project.city,
      rera_number: project.reraNumber ?? "",
      pin_code: project.pinCode ?? "",
      landmark: project.landmark ?? "",
      total_towers: str(project.totalTowers),
      total_floors: str(project.totalFloors),
      flats_per_floor: str(project.flatsPerFloor),
      rate_a: str(project.rateA),
      rate_b: str(project.rateB),
      rate_c: str(project.rateC),
      parking_cost: str(project.parkingCost),
      legal_fees: str(project.legalFees),
      overhead_cost: str(project.overheadCost),
      other_charges: str(project.otherCharges),
      sinking_fund: str(project.sinkingFund),
      amenities_charges: str(project.amenitiesCharges),
    };
    setForm(next);
    // Existing towers as they are (an unchanged Save adds nothing); a project with details but no towers yet
    // gets cards laid out from its details.
    setCards(initialCards(project.towers, detailsOf(next), ratesOf(next)));
    const parking = initialParkingCounts(
      parkingCountsByType(project.towers).byType,
      project.garageOptions ?? [],
      project.totalGarages
    );
    setParkingSelected(parking.selected);
    setParkingCounts(parking.counts);
    setDemandRows(
      (project.demandSchedule ?? []).map((m) => ({ label: m.label, percent: String(m.percent), due_date: m.due_date })),
    );
    setFormError(null);
    setFormOpen(true);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    const payload = {
      name: form.name.trim(),
      builder_name: form.builder_name.trim(),
      location: form.location.trim(),
      city: form.city.trim(),
      rera_number: form.rera_number.trim() || null,
      // Phase-B detail specs + default box-price components (blank → null).
      pin_code: form.pin_code.trim() || null,
      landmark: form.landmark.trim() || null,
      total_towers: intOrNull(form.total_towers),
      total_floors: intOrNull(form.total_floors),
      flats_per_floor: intOrNull(form.flats_per_floor),
      // The parking total is the sum of the per-type counts (kept as declared when none are entered).
      total_garages: parkingTotal(parkingSelected, parkingCounts) || (editingProject?.totalGarages ?? null),
      garage_options: parkingSelected.length ? parkingSelected : null,
      rate_a: numOrNull(form.rate_a),
      rate_b: numOrNull(form.rate_b),
      rate_c: numOrNull(form.rate_c),
      parking_cost: numOrNull(form.parking_cost),
      legal_fees: numOrNull(form.legal_fees),
      overhead_cost: numOrNull(form.overhead_cost),
      other_charges: numOrNull(form.other_charges),
      sinking_fund: numOrNull(form.sinking_fund),
      amenities_charges: numOrNull(form.amenities_charges),
      demand_schedule: (() => {
        const rows = demandRows
          .filter((r) => r.label.trim() && Number(r.percent) > 0 && r.due_date)
          .map((r) => ({ label: r.label.trim(), percent: Number(r.percent), due_date: r.due_date }));
        return rows.length ? rows : null;
      })(),
    };
    // Check the towers before anything is sent, so a half-filled card never saves the project without them.
    const existingTowers = editingProject?.towers ?? [];
    const newUnits =
      cards.reduce(
        (sum, card) => sum + totalOf(plannedAdds(card, existingTowers.find((t) => t.id === card.towerId)?.units ?? [])),
        0
      ) +
      totalOf(plannedParkingAdds(parkingSelected, parkingCounts, parkingCountsByType(existingTowers).byType));
    const layoutError = validateLayout(cards, newUnits);
    if (layoutError) {
      setFormError(layoutError);
      setSaving(false);
      return;
    }
    const towersPayload = cards.map(cardPayload);
    const parking = parkingPayload(parkingSelected, parkingCounts);
    try {
      if (editingProject) {
        // Details first (the parking price comes from them), then build whatever the page adds.
        await inventoryService.updateProject(editingProject.id, payload);
        const result = await inventoryService.syncProjectInventory(editingProject.id, { towers: towersPayload, parking });
        const added = result.created.towers + result.created.units + result.created.parking;
        toast.success("Project updated", added ? `${payload.name} · ${describeCreated(result.created)}` : payload.name);
        if (result.notes.length) toast.info("Existing units kept", result.notes.join(" "));
      } else {
        // One atomic call: project + towers + their units + parking.
        const created = await inventoryService.createProjectFull({ ...payload, towers: towersPayload, parking });
        const built = {
          towers: created.towers.filter((t) => !isParkingBlock(t.name)).length,
          units: created.totalUnits,
          parking: created.totalParking,
        };
        const anyBuilt = built.towers + built.units + built.parking > 0;
        toast.success("Project created", anyBuilt ? `${payload.name} · ${describeCreated(built)}` : payload.name);
      }
      setFormOpen(false);
      await refresh();
    } catch (err) {
      setFormError(extractErrorMessage(err));
      // An Edit whose details saved but whose inventory didn't: show the saved details on the list.
      if (editingProject) void refresh();
    } finally {
      setSaving(false);
    }
  }

  async function confirmArchiveProject() {
    if (!archiveProject) return;
    setArchiving(true);
    try {
      await inventoryService.archiveProject(archiveProject.id);
      toast.success("Project archived", archiveProject.name);
      if (selectedProject?.id === archiveProject.id) setSelectedProject(null);
      setArchiveProject(null);
      await refresh();
    } catch (err) {
      toast.error("Could not archive", extractErrorMessage(err));
    } finally {
      setArchiving(false);
    }
  }

  const columns: DataTableColumn<Project>[] = [
    ...COLUMNS,
    {
      key: "actions",
      header: "",
      render: (p) => (
        <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
          <button
            type="button"
            className="btn btn--ghost btn--icon"
            onClick={(e) => {
              e.stopPropagation();
              openEdit(p);
            }}
            aria-label="Edit project"
          >
            <Pencil size={14} />
          </button>
          <button
            type="button"
            className="btn btn--ghost btn--icon"
            onClick={(e) => {
              e.stopPropagation();
              setArchiveProject(p);
            }}
            aria-label="Archive project"
          >
            <Archive size={14} />
          </button>
        </div>
      ),
    },
  ];

  if (loading && projects.length === 0) return <LoadingBlock label="Loading projects…" />;

  return (
    <div className="projects-page">
      <div className="page-header">
        <h1 className="page-title">Projects</h1>
        <div className="row" style={{ gap: "0.5rem" }}>
          {canExport && (
            <Button
              variant="secondary"
              size="sm"
              icon={<Download size={14} />}
              onClick={() => void exportsService.inventory().catch((e) => toast.error("Export failed", extractErrorMessage(e)))}
            >
              Export CSV
            </Button>
          )}
          <Button variant="primary" icon={<Plus size={16} />} onClick={openCreate}>
            Add Project
          </Button>
        </div>
      </div>

      {projects.length === 0 ? (
        <EmptyState
          icon={<Building2 size={32} />}
          title="No projects yet"
          description="Add your first real-estate project to start managing inventory."
        />
      ) : (
        <Card>
          <DataTable
            columns={columns}
            rows={projects}
            rowKey={(p) => p.id}
            onRowClick={(p) => setSelectedProject(p)}
          />
        </Card>
      )}

      <Modal
        open={formOpen}
        title={editingProject ? "Edit project" : "Add project"}
        size="lg"
        onClose={() => setFormOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setFormOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form="project-form" loading={saving}>
              {editingProject ? "Save changes" : "Create project"}
            </Button>
          </>
        }
      >
        <form id="project-form" className="stack" onSubmit={handleSubmit}>
          <TextField
            id="project-name"
            label="Project name"
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            required
            placeholder="e.g. Prestige Lakeside Habitat"
          />
          <TextField
            id="project-builder"
            label="Builder"
            value={form.builder_name}
            onChange={(event) => setForm({ ...form, builder_name: event.target.value })}
            required
            placeholder="e.g. Prestige Group"
          />
          <div className="form-grid">
            <TextField
              id="project-location"
              label="Location / Area"
              value={form.location}
              onChange={(event) => setForm({ ...form, location: event.target.value })}
              required
              placeholder="e.g. Whitefield"
            />
            <TextField
              id="project-city"
              label="City"
              value={form.city}
              onChange={(event) => setForm({ ...form, city: event.target.value })}
              required
              placeholder="e.g. Bengaluru"
            />
          </div>
          <TextField
            id="project-rera"
            label="RERA number"
            value={form.rera_number}
            onChange={(event) => setForm({ ...form, rera_number: event.target.value })}
            placeholder="Optional"
          />

          {/* Project details (Phase B) — declared specs, all optional. */}
          <div className="stack" style={{ gap: "0.6rem", borderTop: "1px solid var(--color-border)", paddingTop: "0.85rem" }}>
            <strong>Project details</strong>
            <div className="form-grid">
              <TextField id="project-pincode" label="PIN code" value={form.pin_code} onChange={(e) => setForm({ ...form, pin_code: e.target.value })} placeholder="e.g. 560066" />
              <TextField id="project-landmark" label="Landmark" value={form.landmark} onChange={(e) => setForm({ ...form, landmark: e.target.value })} placeholder="e.g. Near ITPL" />
            </div>
            <div className="form-grid">
              <TextField id="project-total-towers" label="Total towers" type="number" min={0} max={100} value={form.total_towers} onChange={(e) => setDetail("total_towers", e.target.value)} />
              <TextField id="project-total-floors" label="Total floors" type="number" min={0} max={200} value={form.total_floors} onChange={(e) => setDetail("total_floors", e.target.value)} />
            </div>
            <div className="form-grid">
              <TextField id="project-flats-per-floor" label="Flats per floor" type="number" min={0} max={200} value={form.flats_per_floor} onChange={(e) => setDetail("flats_per_floor", e.target.value)} />
            </div>
          </div>

          {/* Default pricing (Phase B) — seeds the booking Price Calculator. */}
          <div className="stack" style={{ gap: "0.6rem", borderTop: "1px solid var(--color-border)", paddingTop: "0.85rem" }}>
            <div>
              <strong>Default pricing</strong>
              <p className="muted text-xs" style={{ margin: "0.15rem 0 0" }}>
                Optional — pre-fills the box-price calculator when booking a unit in this project.
              </p>
            </div>
            <div className="form-grid">
              <TextField id="project-rate-a" label="Rate A — Residential (₹/sqft)" type="number" min={0} value={form.rate_a} onChange={(e) => setRate("rate_a", e.target.value)} />
              <TextField id="project-rate-b" label="Rate B — Shop / Commercial (₹/sqft)" type="number" min={0} value={form.rate_b} onChange={(e) => setRate("rate_b", e.target.value)} />
            </div>
            <div className="form-grid">
              <TextField id="project-rate-c" label="Rate C — Godown / Other (₹/sqft)" type="number" min={0} value={form.rate_c} onChange={(e) => setRate("rate_c", e.target.value)} />
              <TextField id="project-parking-cost" label="Garage / Parking (₹)" type="number" min={0} value={form.parking_cost} onChange={(e) => setForm({ ...form, parking_cost: e.target.value })} />
            </div>
            <div className="form-grid">
              <TextField id="project-amenities" label="Amenities / Club (₹)" type="number" min={0} value={form.amenities_charges} onChange={(e) => setForm({ ...form, amenities_charges: e.target.value })} />
              <TextField id="project-sinking-fund" label="Sinking Fund (₹)" type="number" min={0} value={form.sinking_fund} onChange={(e) => setForm({ ...form, sinking_fund: e.target.value })} />
            </div>
            <div className="form-grid">
              <TextField id="project-legal-fees" label="Legal / Documentation (₹)" type="number" min={0} value={form.legal_fees} onChange={(e) => setForm({ ...form, legal_fees: e.target.value })} />
              <TextField id="project-overhead" label="Overhead (₹)" type="number" min={0} value={form.overhead_cost} onChange={(e) => setForm({ ...form, overhead_cost: e.target.value })} />
            </div>
            <TextField id="project-other-charges" label="Other Charges (₹)" type="number" min={0} value={form.other_charges} onChange={(e) => setForm({ ...form, other_charges: e.target.value })} />
          </div>

          <div className="stack" style={{ gap: "0.6rem", borderTop: "1px solid var(--color-border)", paddingTop: "0.85rem" }}>
            <div className="row row--between" style={{ alignItems: "center" }}>
              <div>
                <strong>Demand schedule</strong>
                <p className="muted text-xs" style={{ margin: 0 }}>
                  Payment milestones — % of the unit price on fixed dates. A unit booked in this project inherits these demands.
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                icon={<Plus size={14} />}
                onClick={() => setDemandRows([...demandRows, { label: "", percent: "", due_date: "" }])}
              >
                Add milestone
              </Button>
            </div>
            {demandRows.length > 0 && (
              <div className="muted text-xs">
                Total: {demandRows.reduce((s, r) => s + (Number(r.percent) || 0), 0)}%
              </div>
            )}
            {demandRows.map((r, i) => (
              <div key={i} className="row" style={{ gap: "0.5rem", alignItems: "flex-end" }}>
                <div style={{ flex: 2 }}>
                  <TextField id={`dm-label-${i}`} label="Milestone" maxLength={120} value={r.label} onChange={(e) => setDemandRow(i, { label: e.target.value })} placeholder="e.g. On Booking / Plinth / Possession" />
                </div>
                <div style={{ flex: 1 }}>
                  <TextField id={`dm-pct-${i}`} label="%" type="number" min={0} max={100} value={r.percent} onChange={(e) => setDemandRow(i, { percent: e.target.value })} />
                </div>
                <div style={{ flex: 1.4 }}>
                  <TextField id={`dm-due-${i}`} label="Due date" type="date" value={r.due_date} onChange={(e) => setDemandRow(i, { due_date: e.target.value })} />
                </div>
                <button type="button" className="btn btn--ghost btn--icon" onClick={() => setDemandRows(demandRows.filter((_, idx) => idx !== i))} aria-label="Remove milestone">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
          <ProjectInventoryEditor
            cards={cards}
            onCardsChange={setCards}
            details={detailsOf(form)}
            rates={ratesOf(form)}
            existingTowers={editingProject?.towers ?? []}
            parkingSelected={parkingSelected}
            parkingCounts={parkingCounts}
            onParkingChange={(selected, counts) => {
              setParkingSelected(selected);
              setParkingCounts(counts);
            }}
            existingParking={parkingCountsByType(editingProject?.towers ?? [])}
            declaredGarages={editingProject?.totalGarages ?? null}
          />
          {formError && <div className="error-banner">{formError}</div>}
        </form>
      </Modal>

      {selectedProject && (
        <Modal
          open
          title={selectedProject.name}
          size="lg"
          onClose={() => setSelectedProject(null)}
        >
          <div className="project-detail">
            <div className="project-detail__meta">
              <span><strong>Builder:</strong> {selectedProject.builderName}</span>
              <span><strong>Location:</strong> {selectedProject.location}, {selectedProject.city}</span>
              {selectedProject.reraNumber && (
                <span><strong>RERA:</strong> {selectedProject.reraNumber}</span>
              )}
              <span><strong>Towers:</strong> {selectedProject.towers.filter((t) => !isParkingBlock(t.name)).length}</span>
              <span><strong>Units:</strong> {selectedProject.availableUnits} / {selectedProject.totalUnits} available</span>
              {selectedProject.totalParking > 0 && (
                <span><strong>Parking:</strong> {selectedProject.availableParking} / {selectedProject.totalParking} available</span>
              )}
            </div>

            <h3 className="project-detail__section-title">Possession &amp; Registration</h3>
            <PossessionSummary projectId={selectedProject.id} />

            <h3 className="project-detail__section-title">Towers &amp; Units</h3>
            <TowerManager
              project={selectedProject}
              onChanged={refresh}
              onEditProject={() => {
                const project = selectedProject;
                setSelectedProject(null);
                openEdit(project);
              }}
            />

            <h3 className="project-detail__section-title">Media Repository</h3>
            <MediaGallery project={selectedProject} onChanged={refresh} />
          </div>
        </Modal>
      )}

      <ConfirmDialog
        open={archiveProject !== null}
        title="Archive project?"
        description={
          archiveProject
            ? `${archiveProject.name} and its towers/units will be hidden from inventory. Blocked if any unit is booked, registered or sold.`
            : ""
        }
        confirmLabel="Archive"
        cancelLabel="Cancel"
        loading={archiving}
        onCancel={() => setArchiveProject(null)}
        onConfirm={() => void confirmArchiveProject()}
      />
    </div>
  );
}

// --- Project-wise possession & registration rollup (Phase C3) --------------

function PossessionSummary({ projectId }: { projectId: string }) {
  const [rollup, setRollup] = useState<ProjectPossessionRollup | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    inventoryService
      .getProjectPossession(projectId)
      .then((r) => alive && setRollup(r))
      .catch(() => alive && setRollup(null))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [projectId]);

  if (loading) return <p className="muted text-sm">Loading possession status…</p>;
  if (!rollup) return <p className="muted text-sm">Possession status unavailable.</p>;
  const s = rollup.summary;
  return (
    <div className="row" style={{ gap: "1.5rem", flexWrap: "wrap" }}>
      <span className="text-sm"><span className="muted">Total units</span> <strong>{s.totalUnits}</strong></span>
      <span className="text-sm"><span className="muted">Booked</span> <strong>{s.booked}</strong></span>
      <span className="text-sm"><span className="muted">Registered</span> <strong>{s.registered}</strong></span>
      <span className="text-sm"><span className="muted">Possession complete</span> <strong>{s.possessionComplete}</strong></span>
    </div>
  );
}

// --- Tower + unit management (inside the project detail modal) -------------

function TowerManager({
  project,
  onChanged,
  onEditProject,
}: {
  project: Project;
  onChanged: () => Promise<void> | void;
  onEditProject: () => void;
}) {
  const toast = useToast();

  // Tower edit + per-tower unit list / unit edit + archive confirmation.
  const [editTowerId, setEditTowerId] = useState<string | null>(null);
  const [editTowerName, setEditTowerName] = useState("");
  const [editTowerFloors, setEditTowerFloors] = useState("");
  const [savingTower, setSavingTower] = useState(false);
  const [viewUnitsTowerId, setViewUnitsTowerId] = useState<string | null>(null);
  const [editUnitId, setEditUnitId] = useState<string | null>(null);
  const [unitForm, setUnitForm] = useState({
    unit_number: "",
    unit_type: "residential" as UnitType,
    area: "",
    base_price: "",
    facing: "",
  });
  const [savingUnit, setSavingUnit] = useState(false);
  const [archiveItem, setArchiveItem] = useState<{ kind: "tower" | "unit"; id: string; label: string } | null>(null);
  const [archivingItem, setArchivingItem] = useState(false);

  function startTowerEdit(tower: Tower) {
    setEditTowerId(tower.id);
    setEditTowerName(tower.name);
    setEditTowerFloors(String(tower.totalFloors));
  }

  async function saveTowerEdit(towerId: string) {
    if (!editTowerName.trim()) {
      toast.error("Tower name required");
      return;
    }
    setSavingTower(true);
    try {
      await inventoryService.updateTower(towerId, {
        name: editTowerName.trim(),
        total_floors: parseInt(editTowerFloors, 10) || 1,
      });
      toast.success("Tower updated", editTowerName.trim());
      setEditTowerId(null);
      await onChanged();
    } catch (e) {
      toast.error("Update failed", extractErrorMessage(e));
    } finally {
      setSavingTower(false);
    }
  }

  function startUnitEdit(unit: Unit) {
    setEditUnitId(unit.id);
    setUnitForm({
      unit_number: unit.unitNumber,
      unit_type: unit.unitType,
      area: String(unit.area),
      base_price: String(unit.basePrice),
      facing: unit.facing ?? "",
    });
  }

  async function saveUnitEdit(unitId: string) {
    if (!unitForm.unit_number.trim()) {
      toast.error("Unit number required");
      return;
    }
    setSavingUnit(true);
    try {
      await inventoryService.updateUnit(unitId, {
        unit_number: unitForm.unit_number.trim(),
        unit_type: unitForm.unit_type,
        area: unitForm.area.trim() !== "" ? Number(unitForm.area) : undefined,
        base_price: unitForm.base_price.trim() !== "" ? Number(unitForm.base_price) : undefined,
        facing: unitForm.facing.trim() || null,
      });
      toast.success("Unit updated", unitForm.unit_number.trim());
      setEditUnitId(null);
      await onChanged();
    } catch (e) {
      toast.error("Update failed", extractErrorMessage(e));
    } finally {
      setSavingUnit(false);
    }
  }

  async function confirmArchiveItem() {
    if (!archiveItem) return;
    setArchivingItem(true);
    try {
      if (archiveItem.kind === "tower") await inventoryService.archiveTower(archiveItem.id);
      else await inventoryService.archiveUnit(archiveItem.id);
      toast.success("Archived", archiveItem.label);
      setArchiveItem(null);
      await onChanged();
    } catch (e) {
      toast.error("Could not archive", extractErrorMessage(e));
    } finally {
      setArchivingItem(false);
    }
  }

  return (
    <div className="stack" style={{ gap: "0.75rem" }}>
      <div className="row row--between" style={{ alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
        <p className="muted text-sm" style={{ margin: 0 }}>
          {project.towers.length === 0
            ? "No towers yet. Add towers, flats and parking from Edit project — Save creates them."
            : "To add towers, flats or parking, use Edit project. Here you can view, correct or archive units."}
        </p>
        <Button variant="secondary" size="sm" icon={<Pencil size={14} />} onClick={onEditProject}>
          Edit project
        </Button>
      </div>

      {project.towers.map((tower) => (
        <div key={tower.id} className="card" style={{ padding: "0.75rem 1rem" }}>
          <div className="row row--between" style={{ alignItems: "center" }}>
            <div>
              <strong>{tower.name}</strong>{" "}
              <span className="muted text-sm">· {tower.totalFloors} floors · {tower.units.length} units</span>
            </div>
            <div className="row" style={{ gap: 4, alignItems: "center" }}>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setViewUnitsTowerId(viewUnitsTowerId === tower.id ? null : tower.id)}
              >
                {viewUnitsTowerId === tower.id ? "Hide units" : "Units"}
              </Button>
              <button type="button" className="btn btn--ghost btn--icon" onClick={() => startTowerEdit(tower)} aria-label="Edit tower">
                <Pencil size={14} />
              </button>
              <button
                type="button"
                className="btn btn--ghost btn--icon"
                onClick={() => setArchiveItem({ kind: "tower", id: tower.id, label: tower.name })}
                aria-label="Archive tower"
              >
                <Archive size={14} />
              </button>
            </div>
          </div>

          {editTowerId === tower.id && (
            <div className="form-grid" style={{ marginTop: "0.6rem", alignItems: "end" }}>
              <TextField
                id={`edit-tower-name-${tower.id}`}
                label="Tower name"
                value={editTowerName}
                onChange={(e) => setEditTowerName(e.target.value)}
              />
              <TextField
                id={`edit-tower-floors-${tower.id}`}
                label="Total floors"
                type="number"
                min={1}
                value={editTowerFloors}
                onChange={(e) => setEditTowerFloors(e.target.value)}
              />
              <div className="row" style={{ gap: "0.5rem" }}>
                <Button variant="secondary" size="sm" onClick={() => setEditTowerId(null)}>Cancel</Button>
                <Button size="sm" loading={savingTower} onClick={() => void saveTowerEdit(tower.id)}>Save</Button>
              </div>
            </div>
          )}

          {viewUnitsTowerId === tower.id && (
            <div style={{ marginTop: "0.75rem", overflowX: "auto" }}>
              {tower.units.length === 0 ? (
                <p className="muted text-sm">No units in this tower yet.</p>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left" }}>Unit</th>
                      <th style={{ textAlign: "left" }}>Floor</th>
                      <th style={{ textAlign: "left" }}>Type</th>
                      <th style={{ textAlign: "right" }}>Area</th>
                      <th style={{ textAlign: "right" }}>Price</th>
                      <th style={{ textAlign: "left" }}>Status</th>
                      <th style={{ width: 72 }} />
                    </tr>
                  </thead>
                  <tbody>
                    {tower.units.map((u) =>
                      editUnitId === u.id ? (
                        <tr key={u.id}>
                          <td>
                            <input className="input" value={unitForm.unit_number} onChange={(e) => setUnitForm({ ...unitForm, unit_number: e.target.value })} />
                          </td>
                          <td>{u.floor}</td>
                          <td>
                            <select className="input" value={unitForm.unit_type} onChange={(e) => setUnitForm({ ...unitForm, unit_type: e.target.value as UnitType })}>
                              {UNIT_TYPE_OPTIONS.map((o) => (
                                <option key={o.value} value={o.value}>{o.label}</option>
                              ))}
                            </select>
                          </td>
                          <td><input className="input" type="number" style={{ textAlign: "right" }} value={unitForm.area} onChange={(e) => setUnitForm({ ...unitForm, area: e.target.value })} /></td>
                          <td><input className="input" type="number" style={{ textAlign: "right" }} value={unitForm.base_price} onChange={(e) => setUnitForm({ ...unitForm, base_price: e.target.value })} /></td>
                          <td>{u.status}</td>
                          <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                            <button type="button" className="btn btn--ghost btn--icon" onClick={() => setEditUnitId(null)} aria-label="Cancel">✕</button>
                            <Button size="sm" loading={savingUnit} onClick={() => void saveUnitEdit(u.id)}>Save</Button>
                          </td>
                        </tr>
                      ) : (
                        <tr key={u.id}>
                          <td data-label="Unit"><strong>{u.unitNumber}</strong></td>
                          <td data-label="Floor">{u.floor}</td>
                          <td data-label="Type">{u.unitType}</td>
                          <td data-label="Area" style={{ textAlign: "right" }}>{u.area} {u.areaUnit}</td>
                          <td data-label="Price" style={{ textAlign: "right" }}>{formatInr(u.basePrice)}</td>
                          <td data-label="Status">{u.status}</td>
                          <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                            <button type="button" className="btn btn--ghost btn--icon" onClick={() => startUnitEdit(u)} aria-label="Edit unit"><Pencil size={13} /></button>
                            <button type="button" className="btn btn--ghost btn--icon" onClick={() => setArchiveItem({ kind: "unit", id: u.id, label: u.unitNumber })} aria-label="Archive unit"><Archive size={13} /></button>
                          </td>
                        </tr>
                      )
                    )}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      ))}

      <ConfirmDialog
        open={archiveItem !== null}
        title={archiveItem?.kind === "tower" ? "Archive tower?" : "Archive unit?"}
        description={
          archiveItem
            ? `${archiveItem.label} will be hidden from inventory. ${
                archiveItem.kind === "tower"
                  ? "Blocked if any unit is booked, registered or sold."
                  : "Only available/hold units can be archived."
              }`
            : ""
        }
        confirmLabel="Archive"
        cancelLabel="Cancel"
        loading={archivingItem}
        onCancel={() => setArchiveItem(null)}
        onConfirm={() => void confirmArchiveItem()}
      />
    </div>
  );
}
