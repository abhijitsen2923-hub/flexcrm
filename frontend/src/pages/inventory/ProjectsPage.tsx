import { useEffect, useState, type FormEvent } from "react";
import { Building2, Image, Plus } from "lucide-react";
import { Button, Card, DataTable, EmptyState, Modal, SelectField, TextField, useToast } from "../../components";
import type { DataTableColumn } from "../../components";
import { useInventory } from "../../hooks/useInventory";
import { inventoryService } from "../../services/inventory";
import type { Project, Tower, UnitType } from "../../types/realestate";
import { LoadingBlock } from "../../components/ui/Spinner";
import { extractErrorMessage } from "../../utils/errors";
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

function MediaGallery({ project }: { project: Project }) {
  if (project.media.length === 0) {
    return <p className="media-gallery__empty">No media uploaded yet.</p>;
  }
  return (
    <div className="media-gallery">
      {project.media.map((m) => (
        <a key={m.id} href={m.url} target="_blank" rel="noreferrer" className="media-gallery__item">
          {m.type === "image" ? (
            <img src={m.url} alt={m.label ?? m.type} className="media-gallery__img" />
          ) : (
            <div className="media-gallery__doc">
              <Image size={20} />
              <span>{m.label ?? m.type}</span>
            </div>
          )}
        </a>
      ))}
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
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState<ProjectFormState>(EMPTY_PROJECT_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Keep the open detail modal in sync with refreshed data (after adding
  // towers/units) — selectedProject is a snapshot; re-point it at the fresh row.
  useEffect(() => {
    if (!selectedProject) return;
    const fresh = projects.find((p) => p.id === selectedProject.id);
    if (fresh && fresh !== selectedProject) setSelectedProject(fresh);
  }, [projects, selectedProject]);

  function openCreate() {
    setForm(EMPTY_PROJECT_FORM);
    setFormError(null);
    setCreateOpen(true);
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      await inventoryService.createProject({
        name: form.name.trim(),
        builder_name: form.builder_name.trim(),
        location: form.location.trim(),
        city: form.city.trim(),
        rera_number: form.rera_number.trim() || null,
      });
      toast.success("Project created", form.name.trim());
      setCreateOpen(false);
      await refresh();
    } catch (err) {
      setFormError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <LoadingBlock label="Loading projects…" />;

  return (
    <div className="projects-page">
      <div className="page-header">
        <h1 className="page-title">Projects</h1>
        <Button variant="primary" icon={<Plus size={16} />} onClick={openCreate}>
          Add Project
        </Button>
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
            columns={COLUMNS}
            rows={projects}
            rowKey={(p) => p.id}
            onRowClick={(p) => setSelectedProject(p)}
          />
        </Card>
      )}

      <Modal
        open={createOpen}
        title="Add project"
        onClose={() => setCreateOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreateOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form="create-project-form" loading={saving}>
              Create project
            </Button>
          </>
        }
      >
        <form id="create-project-form" className="stack" onSubmit={handleCreate}>
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
            <MediaGallery project={selectedProject} />
          </div>
        </Modal>
      )}
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
            <Button
              variant="ghost"
              size="sm"
              onClick={() => (unitTowerId === tower.id ? setUnitTowerId(null) : openUnitForm(tower))}
            >
              {unitTowerId === tower.id ? "Close" : "+ Add units"}
            </Button>
          </div>

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
    </div>
  );
}
