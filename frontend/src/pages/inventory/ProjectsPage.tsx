import { useState, type FormEvent } from "react";
import { Building2, Image, Plus } from "lucide-react";
import { Button, Card, DataTable, EmptyState, Modal, TextField, useToast } from "../../components";
import type { DataTableColumn } from "../../components";
import { useInventory } from "../../hooks/useInventory";
import { inventoryService } from "../../services/inventory";
import type { Project } from "../../types/realestate";
import { LoadingBlock } from "../../components/ui/Spinner";
import { extractErrorMessage } from "../../utils/errors";
import "./ProjectsPage.css";

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
            <h3 className="project-detail__section-title">Media Repository</h3>
            <MediaGallery project={selectedProject} />
          </div>
        </Modal>
      )}
    </div>
  );
}
