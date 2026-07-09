import { useCallback, useEffect, useState } from "react";
import { inventoryService } from "../services/inventory";
import { useRealtimeEvent } from "../realtime";
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

  // Keep inventory live across tabs/users: any unit status change (book, confirm,
  // register, sell, cancel, archive) is broadcast — re-pull so views don't go stale.
  useRealtimeEvent((event) => {
    if (event.event === "unit.status_changed") void refresh();
  });

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
