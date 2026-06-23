import { useMemo } from "react";
import { Badge, Card, DataTable, EmptyState, LoadingBlock, type DataTableColumn } from "../../../components";
import { useAuth } from "../../../hooks/useAuth";
import { useLeads } from "../../../hooks/useLeads";
import type { Lead } from "../../../types";
import { pipelineCategoryTone } from "../../../utils/options";
import { usePipelines } from "../../../context/PipelineContext";
import { formatCurrency, formatRelative } from "../../../utils/format";

const QUERY = { page: 1, page_size: 50, industry: "real_estate" as const };

export default function PartnerLeadTrackerPage() {
  const { user } = useAuth();
  const { leads, loading } = useLeads(QUERY);
  const { getStage } = usePipelines();

  // Brokers see only leads they submitted (source = partner_referral from their user).
  // Backend enforces this via token scope; the filter here is a UI convenience only.
  const myLeads = useMemo(
    () => leads.filter((l) => l.source === "partner_referral"),
    [leads]
  );

  const columns: DataTableColumn<Lead>[] = [
    {
      key: "name",
      header: "Buyer",
      render: (l) => (
        <div>
          <div style={{ fontWeight: 600 }}>{l.contact_name || l.title}</div>
          <div className="muted text-xs">{l.contact_phone ?? "—"}</div>
        </div>
      ),
    },
    {
      key: "interest",
      header: "Interest",
      render: (l) => l.interest ?? "—",
    },
    {
      key: "stage",
      header: "Stage",
      render: (l) => {
        const stage = getStage(l.industry, l.stage_code);
        const tone = stage ? pipelineCategoryTone(stage.category) : "neutral";
        return (
          <Badge tone={tone}>{stage ? stage.name : l.stage_code}</Badge>
        );
      },
    },
    {
      key: "value",
      header: "Value",
      align: "right",
      render: (l) => formatCurrency(l.value, l.currency || "INR"),
    },
    {
      key: "updated",
      header: "Updated",
      render: (l) => formatRelative(l.last_comment_at ?? l.updated_at ?? ""),
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

      {myLeads.length === 0 ? (
        <EmptyState
          title="No leads submitted yet"
          description="Use the Submit Lead form to refer your first buyer."
        />
      ) : (
        <Card>
          <DataTable
            columns={columns}
            rows={myLeads}
            rowKey={(l) => l.id}
          />
        </Card>
      )}
    </div>
  );
}
