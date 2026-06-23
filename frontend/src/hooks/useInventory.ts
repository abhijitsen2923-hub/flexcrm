import { useCallback, useEffect, useState } from "react";
import { inventoryService } from "../services/inventory";
import type { Project, UnitStatus } from "../types/realestate";

export function useInventory() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await inventoryService.listProjects();
      setProjects(data);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const updateUnitStatus = useCallback(async (unitId: string, status: UnitStatus) => {
    const updated = await inventoryService.updateUnitStatus(unitId, status);
    setProjects((prev) =>
      prev.map((project) => ({
        ...project,
        towers: project.towers.map((tower) => ({
          ...tower,
          units: tower.units.map((u) => (u.id === unitId ? { ...u, ...updated } : u)),
        })),
      }))
    );
    return updated;
  }, []);

  return { projects, loading, error, refresh, updateUnitStatus };
}
