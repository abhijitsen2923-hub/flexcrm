import type { Project } from "../types/realestate";

export interface UnitLocation {
  projectId: string;
  projectName: string;
  towerName: string;
  unitNumber: string;
}

// Walk the loaded project→tower→unit tree to place a unit. Returns null when the
// unit isn't in the loaded inventory (e.g. archived, or projects not yet loaded).
export function locateUnit(projects: Project[], unitId: string): UnitLocation | null {
  for (const p of projects) {
    for (const t of p.towers) {
      const u = t.units.find((x) => x.id === unitId);
      if (u) return { projectId: p.id, projectName: p.name, towerName: t.name, unitNumber: u.unitNumber };
    }
  }
  return null;
}

export function unitLocationLabel(loc: UnitLocation | null, fallbackUnitId: string): string {
  return loc
    ? `${loc.projectName} · ${loc.towerName} · ${loc.unitNumber}`
    : `Unit ${fallbackUnitId.slice(0, 8)}`;
}

export const NO_PROJECT_ID = "__none__";
export const NO_PROJECT_LABEL = "Unassigned / other";

export interface ProjectGroup<T> {
  projectId: string;
  projectName: string;
  items: T[];
}

// Group booking-like rows by their unit's project, preserving input order within
// each group and first-seen order across groups.
export function groupByProject<T extends { unitId: string }>(
  items: T[],
  projects: Project[],
): ProjectGroup<T>[] {
  const groups = new Map<string, ProjectGroup<T>>();
  for (const item of items) {
    const loc = locateUnit(projects, item.unitId);
    const projectId = loc?.projectId ?? NO_PROJECT_ID;
    const projectName = loc?.projectName ?? NO_PROJECT_LABEL;
    let group = groups.get(projectId);
    if (!group) {
      group = { projectId, projectName, items: [] };
      groups.set(projectId, group);
    }
    group.items.push(item);
  }
  return Array.from(groups.values());
}
