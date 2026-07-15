import { useEffect, useState } from "react";
import { Badge, Card, DataTable, EmptyState, LoadingBlock, useToast, type DataTableColumn } from "../../../components";
import { partnerPortalService } from "../../../services/partnerPortal";
import { extractErrorMessage } from "../../../utils/errors";
import { formatInr, formatRelative } from "../../../utils/format";
import { pipelineCategoryTone } from "../../../utils/options";
import { usePipelines } from "../../../context/PipelineContext";
import type { PartnerLeadRow } from "../../../types/partner";

export default function PartnerLeadTrackerPage() {
  const [leads, setLeads] = useState<PartnerLeadRow[]>([]);
  const [loading, setLoading] = useState(true);
  const { getStage } = usePipelines();
  const toast = useToast();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void partnerPortalService
      .leads()
      .then((rows) => { if (!cancelled) setLeads(rows); })
      .catch((err) => { if (!cancelled) toast.error("Could not load your leads", extractErrorMessage(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [toast]);

  const columns: DataTableColumn<PartnerLeadRow>[] = [
    {
      key: "name",
      header: "Buyer",
      render: (l) => (
        <div>
          <div style={{ fontWeight: 600 }}>{l.contact_name || l.title}</div>
          <div className="muted text-xs">#{l.lead_number}</div>
        </div>
      ),
    },
    {
      key: "requirement",
      header: "Requirement",
      render: (l) => (
        <div>
          <div>{l.property_type ?? "—"}</div>
          <div className="muted text-xs">{l.preferred_location ?? ""}</div>
        </div>
      ),
    },
    {
      key: "budget",
      header: "Budget",
      align: "right",
      render: (l) =>
        l.budget_min || l.budget_max
          ? `${l.budget_min ? formatInr(Number(l.budget_min)) : "—"} – ${l.budget_max ? formatInr(Number(l.budget_max)) : "—"}`
          : "—",
    },
    {
      key: "stage",
      header: "Stage",
      render: (l) => {
        const stage = getStage("real_estate", l.stage_code);
        const tone = stage ? pipelineCategoryTone(stage.category) : "neutral";
        return <Badge tone={tone}>{stage ? stage.name : l.stage_code}</Badge>;
      },
    },
    {
      key: "created",
      header: "Referred",
      render: (l) => formatRelative(l.created_at),
    },
  ];

  if (loading) return <LoadingBlock label="Loading your leads…" />;

  return (
    <div>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>My Leads</h1>
          <p>Real-estate leads you have referred — live pipeline status.</p>
        </div>
      </div>

      {leads.length === 0 ? (
        <EmptyState
          title="No leads submitted yet"
          description="Use the Submit Lead form to refer your first buyer."
        />
      ) : (
        <Card>
          <DataTable columns={columns} rows={leads} rowKey={(l) => l.id} />
        </Card>
      )}
    </div>
  );
}
