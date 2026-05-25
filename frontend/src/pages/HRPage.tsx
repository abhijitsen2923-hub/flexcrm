import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  Badge,
  Button,
  DataTable,
  EmptyState,
  LoadingBlock,
  useToast,
  type DataTableColumn
} from "../components";
import { usePermissions } from "../hooks/usePermissions";
import { hrService } from "../services/hr";
import type { ScorecardRow, TeamScorecard } from "../types";
import { extractErrorMessage } from "../utils/errors";
import { formatCurrency } from "../utils/format";


function gradeTone(grade: string): "success" | "info" | "warning" | "danger" | "neutral" {
  if (grade === "A+" || grade === "A") return "success";
  if (grade === "B+" || grade === "B") return "info";
  if (grade === "C") return "warning";
  if (grade === "D") return "danger";
  return "neutral";
}


export default function HRPage() {
  const [scorecard, setScorecard] = useState<TeamScorecard | null>(null);
  const [loading, setLoading] = useState(false);
  const [recomputingUserId, setRecomputingUserId] = useState<string | null>(null);
  const toast = useToast();
  const { has: hasPerm } = usePermissions();
  const canManage = hasPerm("HR_MANAGE");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setScorecard(await hrService.teamScorecard());
    } catch (error) {
      toast.error("Could not load HR scorecard", extractErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void load();
  }, [load]);

  async function recompute(userId: string) {
    setRecomputingUserId(userId);
    try {
      await hrService.recompute(userId);
      toast.success("Recomputed", `Snapshot refreshed`);
      await load();
    } catch (error) {
      toast.error("Recompute failed", extractErrorMessage(error));
    } finally {
      setRecomputingUserId(null);
    }
  }

  const columns: DataTableColumn<ScorecardRow>[] = [
    { key: "name", header: "Salesperson", render: (row) => <strong>{row.user_name}</strong> },
    { key: "deals", header: "Deals", align: "right", render: (row) => row.deals_closed },
    { key: "revenue", header: "Revenue", align: "right", render: (row) => formatCurrency(row.revenue) },
    { key: "collections", header: "Collections", align: "right", render: (row) => formatCurrency(row.collections) },
    { key: "conv", header: "Conv. rate", align: "right", render: (row) => `${row.conversion_rate}%` },
    { key: "score", header: "Score", align: "right", render: (row) => <strong>{row.score}</strong> },
    { key: "grade", header: "Grade", render: (row) => <Badge tone={gradeTone(row.grade)}>{row.grade}</Badge> },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (row) =>
        canManage ? (
          <Button
            size="sm"
            variant="ghost"
            loading={recomputingUserId === row.user_id}
            onClick={() => void recompute(row.user_id)}
          >
            Recompute
          </Button>
        ) : null
    }
  ];

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>HR Performance</h1>
          <p>Per-salesperson scorecard. Computed nightly; manual recompute available per row.</p>
        </div>
        <div className="page-header__actions">
          <Button variant="secondary" size="sm" icon={<RefreshCw size={14} />} onClick={() => void load()} loading={loading}>
            Refresh
          </Button>
        </div>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="row row--between" style={{ padding: "1rem 1.25rem", borderBottom: "1px solid var(--color-border)" }}>
          <span className="muted">Snapshot date: {scorecard?.snapshot_date ?? "—"}</span>
        </div>
        <div className="table-wrap" style={{ border: "none", boxShadow: "none" }}>
          {loading && !scorecard ? (
            <LoadingBlock label="Loading scorecard…" />
          ) : (
            <DataTable
              columns={columns}
              rows={scorecard?.rows ?? []}
              rowKey={(row) => row.user_id}
              empty={
                <EmptyState
                  title="No snapshots yet"
                  description="Recompute a user manually, or run `python -m app.jobs.scorecard_compute` to seed today's snapshots."
                />
              }
            />
          )}
        </div>
      </div>
    </>
  );
}
