import { useState } from "react";
import { Building2, Image, Plus } from "lucide-react";
import { Button, Card, DataTable, EmptyState, Modal } from "../../components";
import type { DataTableColumn } from "../../components";
import { useInventory } from "../../hooks/useInventory";
import type { Project } from "../../types/realestate";
import { LoadingBlock } from "../../components/ui/Spinner";
import "./ProjectsPage.css";

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
  const { projects, loading } = useInventory();
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);

  if (loading) return <LoadingBlock label="Loading projects…" />;

  return (
    <div className="projects-page">
      <div className="page-header">
        <h1 className="page-title">Projects</h1>
        <Button variant="primary" icon={<Plus size={16} />}>
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
