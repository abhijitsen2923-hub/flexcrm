import { useEffect, useRef, useState } from "react";
import { Archive, Building2, Download, Image, Pencil, Plus, Trash2, Upload } from "lucide-react";
import { Button, Card, ConfirmDialog, DataTable, EmptyState, Modal, SelectField, TextField, useToast } from "../../components";
import type { DataTableColumn } from "../../components";
import { useInventory } from "../../hooks/useInventory";
import { usePermissions } from "../../hooks/usePermissions";
import { inventoryService } from "../../services/inventory";
import { exportsService } from "../../services/exports";
import type { Project, ProjectMedia, ProjectPossessionRollup, Tower, Unit, UnitType } from "../../types/realestate";
import { LoadingBlock } from "../../components/ui/Spinner";
import { extractErrorMessage } from "../../utils/errors";
import { formatInr } from "../../utils/format";
import { isParkingBlock } from "../../utils/projectInventory";
import { CONFIGURATION_SUGGESTIONS } from "../../utils/projectWizard";
import { ProjectPaymentPlanPanel } from "./components/ProjectPaymentPlanPanel";
import { ProjectWizard } from "./components/ProjectWizard";
import "./ProjectsPage.css";

const UNIT_TYPE_OPTIONS: { value: UnitType; label: string }[] = [
  { value: "residential", label: "Residential / Flat" },
  { value: "parking", label: "Parking" },
  { value: "shop", label: "Shop / Commercial" },
  { value: "godown", label: "Godown / Warehouse" },
];

// "Type A · 2 BHK · PLC" for the units table (older units have no flat type).
function flatTypeText(u: Unit): string {
  const parts = [u.flatType ? `Type ${u.flatType}` : null, u.configuration, u.hasPlc ? "PLC" : null].filter(Boolean);
  return parts.length ? parts.join(" · ") : "—";
}

// Floor by floor, then A-101, A-102 … (numbers compared as numbers, so A-110 comes after A-109).
function byFloorAndNumber(a: Unit, b: Unit): number {
  return a.floor - b.floor || a.unitNumber.localeCompare(b.unitNumber, undefined, { numeric: true });
}

// Blank → null (clears it); anything else must be a size above 0.
function areaOrNull(value: string): number | null | "invalid" {
  const t = value.trim();
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) && n > 0 ? n : "invalid";
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
  // The Add / Edit wizard: open with the project being edited (null = Add). `wizardRun` remounts it per opening so
  // it always starts fresh.
  const [wizard, setWizard] = useState<{ project: Project | null; run: number } | null>(null);
  const wizardRun = useRef(0);
  const [archiveProject, setArchiveProject] = useState<Project | null>(null);
  const [archiving, setArchiving] = useState(false);

  // Keep the open detail modal in sync with refreshed data (after adding
  // towers/units) — selectedProject is a snapshot; re-point it at the fresh row.
  // Only when the list changes: a newer copy set from the detail screen (e.g. a
  // milestone marked reached) must not be swapped back for the older list row.
  useEffect(() => {
    setSelectedProject((current) => {
      if (!current) return current;
      return projects.find((p) => p.id === current.id) ?? current;
    });
  }, [projects]);

  function openCreate() {
    wizardRun.current += 1;
    setWizard({ project: null, run: wizardRun.current });
  }

  function openEdit(project: Project) {
    wizardRun.current += 1;
    setWizard({ project, run: wizardRun.current });
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

      {wizard && (
        <ProjectWizard
          key={wizard.run}
          project={wizard.project}
          onClose={() => setWizard(null)}
          onSaved={async () => {
            setWizard(null);
            await refresh();
          }}
          onPartlySaved={() => void refresh()}
        />
      )}

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

            <h3 className="project-detail__section-title">Payment plan</h3>
            <ProjectPaymentPlanPanel
              project={selectedProject}
              onChanged={(updated) => {
                setSelectedProject(updated);
                void refresh();
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
    carpet_area: "",
    built_up_area: "",
    base_price: "",
    facing: "",
    flat_type: "",
    configuration: "",
    has_plc: false,
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
      carpet_area: unit.carpetArea != null ? String(unit.carpetArea) : "",
      built_up_area: unit.builtUpArea != null ? String(unit.builtUpArea) : "",
      base_price: String(unit.basePrice),
      facing: unit.facing ?? "",
      flat_type: unit.flatType ?? "",
      configuration: unit.configuration ?? "",
      has_plc: unit.hasPlc,
    });
  }

  async function saveUnitEdit(unitId: string) {
    if (!unitForm.unit_number.trim()) {
      toast.error("Unit number required");
      return;
    }
    const carpet = areaOrNull(unitForm.carpet_area);
    const builtUp = areaOrNull(unitForm.built_up_area);
    if (carpet === "invalid" || builtUp === "invalid") {
      toast.error("Check the areas", "Carpet and built-up must be above 0, or left blank.");
      return;
    }
    const flatType = unitForm.flat_type.trim().toUpperCase();
    const isFlat = unitForm.unit_type === "residential";
    if (isFlat && flatType && !/^[A-Z]{1,2}$/.test(flatType)) {
      toast.error("Check the flat type", "Use its letter, e.g. A (or AA).");
      return;
    }
    setSavingUnit(true);
    try {
      await inventoryService.updateUnit(unitId, {
        unit_number: unitForm.unit_number.trim(),
        unit_type: unitForm.unit_type,
        area: unitForm.area.trim() !== "" ? Number(unitForm.area) : undefined,
        carpet_area: carpet,
        built_up_area: builtUp,
        base_price: unitForm.base_price.trim() !== "" ? Number(unitForm.base_price) : undefined,
        facing: unitForm.facing.trim() || null,
        // Flat type / configuration / PLC belong to flats: a unit re-categorised as a shop, godown or parking spot
        // drops them (else it would still read "Type C · 2 BHK" and the price calculator would add PLC).
        ...(isFlat
          ? { flat_type: flatType || null, configuration: unitForm.configuration.trim() || null, has_plc: unitForm.has_plc }
          : { flat_type: null, configuration: null, has_plc: false }),
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

      <datalist id="unit-fix-configurations">
        {CONFIGURATION_SUGGESTIONS.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>

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
                      <th style={{ textAlign: "left" }}>Category</th>
                      <th style={{ textAlign: "left" }}>Flat type</th>
                      <th style={{ textAlign: "right" }}>Area</th>
                      <th style={{ textAlign: "right" }}>Price</th>
                      <th style={{ textAlign: "left" }}>Status</th>
                      <th style={{ width: 72 }} />
                    </tr>
                  </thead>
                  <tbody>
                    {[...tower.units].sort(byFloorAndNumber).map((u) =>
                      editUnitId === u.id ? (
                        <tr key={u.id}>
                          <td colSpan={8} className="unit-fix__cell">
                            <div className="unit-fix">
                              <div>
                                <strong>Correct {u.unitNumber}</strong>
                                <span className="muted text-sm"> · floor {u.floor} · {u.status}</span>
                              </div>
                              <div className="unit-fix__grid">
                                <TextField id={`uf-number-${u.id}`} label="Unit number" value={unitForm.unit_number} onChange={(e) => setUnitForm({ ...unitForm, unit_number: e.target.value })} />
                                <SelectField
                                  id={`uf-category-${u.id}`}
                                  label="Category"
                                  value={unitForm.unit_type}
                                  options={UNIT_TYPE_OPTIONS}
                                  onChange={(e) => setUnitForm({ ...unitForm, unit_type: e.target.value as UnitType })}
                                />
                                {unitForm.unit_type === "residential" && (
                                  <>
                                    <TextField
                                      id={`uf-flat-type-${u.id}`}
                                      label="Flat type"
                                      value={unitForm.flat_type}
                                      maxLength={2}
                                      placeholder="e.g. A"
                                      onChange={(e) => setUnitForm({ ...unitForm, flat_type: e.target.value.toUpperCase() })}
                                    />
                                    <TextField
                                      id={`uf-config-${u.id}`}
                                      label="Configuration"
                                      list="unit-fix-configurations"
                                      maxLength={32}
                                      value={unitForm.configuration}
                                      placeholder="e.g. 2 BHK"
                                      onChange={(e) => setUnitForm({ ...unitForm, configuration: e.target.value })}
                                    />
                                  </>
                                )}
                                <TextField id={`uf-area-${u.id}`} label="Super built-up (sq ft)" type="number" min={0} value={unitForm.area} onChange={(e) => setUnitForm({ ...unitForm, area: e.target.value })} />
                                <TextField id={`uf-carpet-${u.id}`} label="Carpet (sq ft)" type="number" min={0} value={unitForm.carpet_area} onChange={(e) => setUnitForm({ ...unitForm, carpet_area: e.target.value })} />
                                <TextField id={`uf-built-${u.id}`} label="Built-up (sq ft)" type="number" min={0} value={unitForm.built_up_area} onChange={(e) => setUnitForm({ ...unitForm, built_up_area: e.target.value })} />
                                <TextField id={`uf-price-${u.id}`} label="Price (₹)" type="number" min={0} value={unitForm.base_price} onChange={(e) => setUnitForm({ ...unitForm, base_price: e.target.value })} />
                              </div>
                              <div className="row row--between" style={{ alignItems: "center", gap: "0.5rem" }}>
                                {unitForm.unit_type === "residential" ? (
                                  <label className="row text-sm" style={{ gap: 6, cursor: "pointer" }}>
                                    <input type="checkbox" checked={unitForm.has_plc} onChange={(e) => setUnitForm({ ...unitForm, has_plc: e.target.checked })} />
                                    PLC — corner / view (adds the PLC charge)
                                  </label>
                                ) : (
                                  <span />
                                )}
                                <div className="row" style={{ gap: "0.5rem" }}>
                                  <Button variant="secondary" size="sm" onClick={() => setEditUnitId(null)}>Cancel</Button>
                                  <Button size="sm" loading={savingUnit} onClick={() => void saveUnitEdit(u.id)}>Save</Button>
                                </div>
                              </div>
                            </div>
                          </td>
                        </tr>
                      ) : (
                        <tr key={u.id}>
                          <td data-label="Unit"><strong>{u.unitNumber}</strong></td>
                          <td data-label="Floor">{u.floor}</td>
                          <td data-label="Category">{UNIT_TYPE_OPTIONS.find((o) => o.value === u.unitType)?.label ?? u.unitType}</td>
                          <td data-label="Flat type">{flatTypeText(u)}</td>
                          <td data-label="Area" style={{ textAlign: "right" }}>
                            {u.area} {u.areaUnit}
                            {(u.carpetArea != null || u.builtUpArea != null) && (
                              <div className="muted text-xs">
                                {[u.carpetArea != null ? `Carpet ${u.carpetArea}` : null, u.builtUpArea != null ? `Built-up ${u.builtUpArea}` : null]
                                  .filter(Boolean)
                                  .join(" · ")}
                              </div>
                            )}
                          </td>
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
