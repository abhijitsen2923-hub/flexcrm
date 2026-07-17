import { useEffect, useRef, useState, type FormEvent } from "react";
import { Archive, Building2, Download, Image, Pencil, Plus, Trash2, Upload } from "lucide-react";
import { Button, Card, ConfirmDialog, DataTable, EmptyState, Modal, SelectField, TextField, useToast } from "../../components";
import type { DataTableColumn } from "../../components";
import { useInventory } from "../../hooks/useInventory";
import { usePermissions } from "../../hooks/usePermissions";
import { inventoryService } from "../../services/inventory";
import { exportsService } from "../../services/exports";
import type { Project, ProjectMedia, Tower, Unit, UnitType } from "../../types/realestate";
import { LoadingBlock } from "../../components/ui/Spinner";
import { extractErrorMessage } from "../../utils/errors";
import { formatInr } from "../../utils/format";
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
}

const EMPTY_PROJECT_FORM: ProjectFormState = {
  name: "",
  builder_name: "",
  location: "",
  city: "",
  rera_number: "",
};

// One tower row in the combined Add-Project form (+ its optional unit batch).
interface TowerBuilder {
  name: string;
  total_floors: string;
  addUnits: boolean;
  unit_type: UnitType;
  units_per_floor: string;
  area: string;
  base_price: string;
  unit_prefix: string;
}

const EMPTY_TOWER: TowerBuilder = {
  name: "",
  total_floors: "10",
  addUnits: true,
  unit_type: "residential",
  units_per_floor: "4",
  area: "1000",
  base_price: "5000000",
  unit_prefix: "",
};

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
  const [towers, setTowers] = useState<TowerBuilder[]>([{ ...EMPTY_TOWER }]);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function setTower(i: number, patch: Partial<TowerBuilder>) {
    setTowers((prev) => prev.map((t, idx) => (idx === i ? { ...t, ...patch } : t)));
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
    setTowers([{ ...EMPTY_TOWER }]);
    setFormError(null);
    setFormOpen(true);
  }

  function openEdit(project: Project) {
    setEditingProject(project);
    setForm({
      name: project.name,
      builder_name: project.builderName,
      location: project.location,
      city: project.city,
      rera_number: project.reraNumber ?? "",
    });
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
    };
    try {
      if (editingProject) {
        await inventoryService.updateProject(editingProject.id, payload);
        toast.success("Project updated", payload.name);
      } else {
        // Combined create: project + towers + each tower's units, atomic.
        const towersPayload = towers
          .filter((t) => t.name.trim())
          .map((t) => {
            const floors = Math.max(1, Number(t.total_floors) || 1);
            const perFloor = Number(t.units_per_floor) || 0;
            const units =
              t.addUnits && perFloor > 0
                ? {
                    unit_type: t.unit_type,
                    floors: Array.from({ length: floors }, (_, i) => ({ floor: i + 1, count: perFloor })),
                    area: Number(t.area) || 1,
                    base_price: Number(t.base_price) || 0,
                    unit_prefix: t.unit_prefix.trim() || undefined,
                  }
                : null;
            return { name: t.name.trim(), total_floors: floors, units };
          });
        await inventoryService.createProjectFull({ ...payload, towers: towersPayload });
        toast.success("Project created", `${payload.name}${towersPayload.length ? ` · ${towersPayload.length} tower(s)` : ""}`);
      }
      setFormOpen(false);
      await refresh();
    } catch (err) {
      setFormError(extractErrorMessage(err));
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

  if (loading) return <LoadingBlock label="Loading projects…" />;

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

          {!editingProject && (
            <div className="stack" style={{ gap: "0.6rem", borderTop: "1px solid var(--color-border)", paddingTop: "0.85rem" }}>
              <div className="row row--between" style={{ alignItems: "center" }}>
                <strong>Towers &amp; units</strong>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  icon={<Plus size={14} />}
                  onClick={() => setTowers([...towers, { ...EMPTY_TOWER }])}
                >
                  Add tower
                </Button>
              </div>
              <p className="muted text-xs" style={{ margin: 0 }}>
                Add one or more towers now, each with its units. You can always add more later from the project.
              </p>
              {towers.map((t, i) => {
                const count = (Number(t.total_floors) || 0) * (Number(t.units_per_floor) || 0);
                return (
                  <div key={i} className="card" style={{ padding: "0.75rem", background: "var(--color-surface-muted)" }}>
                    <div className="row row--between" style={{ alignItems: "center", marginBottom: "0.4rem" }}>
                      <span className="muted text-xs">Tower {i + 1}</span>
                      {towers.length > 1 && (
                        <button
                          type="button"
                          className="btn btn--ghost btn--icon"
                          onClick={() => setTowers(towers.filter((_, idx) => idx !== i))}
                          aria-label="Remove tower"
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                    <div className="form-grid">
                      <TextField id={`tower-name-${i}`} label="Tower name" value={t.name} onChange={(e) => setTower(i, { name: e.target.value })} placeholder="e.g. Tower A" />
                      <TextField id={`tower-floors-${i}`} label="Total floors" type="number" min={1} value={t.total_floors} onChange={(e) => setTower(i, { total_floors: e.target.value })} />
                    </div>
                    <label className="row" style={{ gap: "0.4rem", alignItems: "center", margin: "0.55rem 0 0.3rem" }}>
                      <input type="checkbox" checked={t.addUnits} onChange={(e) => setTower(i, { addUnits: e.target.checked })} />
                      <span className="text-sm">Generate units for this tower</span>
                    </label>
                    {t.addUnits && (
                      <>
                        <div className="form-grid">
                          <SelectField id={`tower-utype-${i}`} label="Unit type" value={t.unit_type} onChange={(e) => setTower(i, { unit_type: e.target.value as UnitType })} options={UNIT_TYPE_OPTIONS} />
                          <TextField id={`tower-perfloor-${i}`} label="Units per floor" type="number" min={1} value={t.units_per_floor} onChange={(e) => setTower(i, { units_per_floor: e.target.value })} />
                        </div>
                        <div className="form-grid">
                          <TextField id={`tower-area-${i}`} label="Area (sqft)" type="number" min={1} value={t.area} onChange={(e) => setTower(i, { area: e.target.value })} />
                          <TextField id={`tower-price-${i}`} label="Base price (₹)" type="number" min={0} value={t.base_price} onChange={(e) => setTower(i, { base_price: e.target.value })} />
                        </div>
                        <TextField
                          id={`tower-prefix-${i}`}
                          label="Unit no. prefix (optional)"
                          value={t.unit_prefix}
                          onChange={(e) => setTower(i, { unit_prefix: e.target.value })}
                          placeholder="e.g. A"
                          hint={count > 0 ? `${count} units will be created` : undefined}
                        />
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          )}
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
              <span><strong>Towers:</strong> {selectedProject.towers.length}</span>
              <span><strong>Total Units:</strong> {selectedProject.totalUnits}</span>
            </div>

            <h3 className="project-detail__section-title">Towers &amp; Units</h3>
            <TowerManager project={selectedProject} onChanged={refresh} />

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

// --- Tower + unit management (inside the project detail modal) -------------

function TowerManager({ project, onChanged }: { project: Project; onChanged: () => Promise<void> | void }) {
  const toast = useToast();
  const [showTowerForm, setShowTowerForm] = useState(false);
  const [towerName, setTowerName] = useState("");
  const [towerFloors, setTowerFloors] = useState("10");
  const [addingTower, setAddingTower] = useState(false);

  // Unit-batch form (targets one tower at a time).
  const [unitTowerId, setUnitTowerId] = useState<string | null>(null);
  const [unitType, setUnitType] = useState<UnitType>("residential");
  const [floorFrom, setFloorFrom] = useState("1");
  const [floorTo, setFloorTo] = useState("1");
  const [sameCount, setSameCount] = useState(true);
  const [perFloor, setPerFloor] = useState("4");
  const [customCounts, setCustomCounts] = useState<Record<number, string>>({});
  const [area, setArea] = useState("1000");
  const [basePrice, setBasePrice] = useState("5000000");
  const [prefix, setPrefix] = useState("");
  const [savingUnits, setSavingUnits] = useState(false);

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

  async function addTower() {
    const floors = parseInt(towerFloors, 10);
    if (!towerName.trim() || !floors || floors < 1) {
      toast.error("Enter a tower name and floor count");
      return;
    }
    setAddingTower(true);
    try {
      await inventoryService.createTower(project.id, { name: towerName.trim(), total_floors: floors });
      toast.success("Tower added", towerName.trim());
      setTowerName("");
      setShowTowerForm(false);
      await onChanged();
    } catch (e) {
      toast.error("Failed to add tower", extractErrorMessage(e));
    } finally {
      setAddingTower(false);
    }
  }

  function openUnitForm(tower: Tower) {
    setUnitTowerId(tower.id);
    setUnitType("residential");
    setFloorFrom("1");
    setFloorTo(String(tower.totalFloors || 1));
    setSameCount(true);
    setPerFloor("4");
    setCustomCounts({});
    setArea("1000");
    setBasePrice("5000000");
    setPrefix("");
  }

  function floorRange(): number[] {
    const a = parseInt(floorFrom, 10);
    const b = parseInt(floorTo, 10);
    if (isNaN(a) || isNaN(b) || b < a) return [];
    return Array.from({ length: b - a + 1 }, (_, i) => a + i);
  }

  async function addUnits(towerId: string) {
    const floors = floorRange()
      .map((f) => ({
        floor: f,
        count: sameCount ? parseInt(perFloor, 10) || 0 : parseInt(customCounts[f] || "0", 10) || 0,
      }))
      .filter((x) => x.count > 0);
    if (floors.length === 0) {
      toast.error("Enter at least one unit count");
      return;
    }
    if (!(Number(area) > 0)) {
      toast.error("Area must be greater than 0");
      return;
    }
    setSavingUnits(true);
    try {
      await inventoryService.createUnitsBatch(towerId, {
        unit_type: unitType,
        floors,
        area: Number(area),
        base_price: Number(basePrice) || 0,
        unit_prefix: prefix.trim() || null,
      });
      const total = floors.reduce((n, x) => n + x.count, 0);
      toast.success("Units added", `${total} ${unitType} unit${total === 1 ? "" : "s"}`);
      setUnitTowerId(null);
      await onChanged();
    } catch (e) {
      toast.error("Failed to add units", extractErrorMessage(e));
    } finally {
      setSavingUnits(false);
    }
  }

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
      {project.towers.length === 0 && !showTowerForm && (
        <p className="muted text-sm">No towers yet. Add a tower, then add its units.</p>
      )}

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
              <Button
                variant="ghost"
                size="sm"
                onClick={() => (unitTowerId === tower.id ? setUnitTowerId(null) : openUnitForm(tower))}
              >
                {unitTowerId === tower.id ? "Close" : "+ Add units"}
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

          {unitTowerId === tower.id && (
            <div className="stack" style={{ marginTop: "0.75rem", gap: "0.6rem" }}>
              <SelectField
                id={`unit-type-${tower.id}`}
                label="Unit type"
                value={unitType}
                onChange={(e) => setUnitType(e.target.value as UnitType)}
                options={UNIT_TYPE_OPTIONS}
              />
              <div className="form-grid">
                <TextField
                  id={`floor-from-${tower.id}`}
                  label="From floor"
                  type="number"
                  min={0}
                  value={floorFrom}
                  onChange={(e) => setFloorFrom(e.target.value)}
                />
                <TextField
                  id={`floor-to-${tower.id}`}
                  label="To floor"
                  type="number"
                  min={0}
                  value={floorTo}
                  onChange={(e) => setFloorTo(e.target.value)}
                />
              </div>

              <div className="row" style={{ gap: "1rem", flexWrap: "wrap" }}>
                <label style={{ display: "flex", gap: 6, alignItems: "center", cursor: "pointer" }}>
                  <input type="radio" checked={sameCount} onChange={() => setSameCount(true)} />
                  Same count on every floor
                </label>
                <label style={{ display: "flex", gap: 6, alignItems: "center", cursor: "pointer" }}>
                  <input type="radio" checked={!sameCount} onChange={() => setSameCount(false)} />
                  Custom per floor
                </label>
              </div>

              {sameCount ? (
                <TextField
                  id={`per-floor-${tower.id}`}
                  label="Units per floor"
                  type="number"
                  min={1}
                  value={perFloor}
                  onChange={(e) => setPerFloor(e.target.value)}
                />
              ) : (
                <div>
                  <span className="muted text-xs">Units on each floor</span>
                  <div className="row" style={{ flexWrap: "wrap", gap: "0.4rem", marginTop: "0.35rem" }}>
                    {floorRange().map((f) => (
                      <label key={f} style={{ display: "flex", flexDirection: "column", width: 64 }}>
                        <span className="muted text-xs">F{f}</span>
                        <input
                          className="input"
                          type="number"
                          min={0}
                          value={customCounts[f] ?? ""}
                          placeholder="0"
                          onChange={(e) => setCustomCounts({ ...customCounts, [f]: e.target.value })}
                        />
                      </label>
                    ))}
                  </div>
                </div>
              )}

              <div className="form-grid">
                <TextField
                  id={`area-${tower.id}`}
                  label="Area (sqft)"
                  type="number"
                  min={1}
                  value={area}
                  onChange={(e) => setArea(e.target.value)}
                />
                <TextField
                  id={`price-${tower.id}`}
                  label="Base price (₹)"
                  type="number"
                  min={0}
                  step="100000"
                  value={basePrice}
                  onChange={(e) => setBasePrice(e.target.value)}
                />
              </div>
              <TextField
                id={`prefix-${tower.id}`}
                label="Unit number prefix"
                value={prefix}
                onChange={(e) => setPrefix(e.target.value)}
                placeholder="Optional — defaults R/P/S/G by type"
              />
              <div className="row" style={{ justifyContent: "flex-end" }}>
                <Button loading={savingUnits} onClick={() => void addUnits(tower.id)}>
                  Create units
                </Button>
              </div>
            </div>
          )}
        </div>
      ))}

      {showTowerForm ? (
        <div className="card" style={{ padding: "0.75rem 1rem" }}>
          <div className="form-grid">
            <TextField
              id="new-tower-name"
              label="Tower name"
              value={towerName}
              onChange={(e) => setTowerName(e.target.value)}
              placeholder="e.g. Tower A"
            />
            <TextField
              id="new-tower-floors"
              label="Total floors"
              type="number"
              min={1}
              value={towerFloors}
              onChange={(e) => setTowerFloors(e.target.value)}
            />
          </div>
          <div className="row" style={{ justifyContent: "flex-end", gap: "0.5rem", marginTop: "0.5rem" }}>
            <Button variant="secondary" onClick={() => setShowTowerForm(false)} disabled={addingTower}>
              Cancel
            </Button>
            <Button loading={addingTower} onClick={() => void addTower()}>
              Add tower
            </Button>
          </div>
        </div>
      ) : (
        <Button variant="secondary" size="sm" icon={<Plus size={14} />} onClick={() => setShowTowerForm(true)}>
          Add tower
        </Button>
      )}

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
