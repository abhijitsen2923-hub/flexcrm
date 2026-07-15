import { useEffect, useState } from "react";
import { Badge, Card, DataTable, EmptyState, LoadingBlock, useToast, type DataTableColumn } from "../../../components";
import { partnerPortalService } from "../../../services/partnerPortal";
import { extractErrorMessage } from "../../../utils/errors";
import { formatDate, formatInr } from "../../../utils/format";
import type { BrokeragePayout } from "../../../types/partner";

const STATUS_TONE = {
  accrued: "info",
  paid: "success",
  reversed: "danger",
} as const;

export default function PartnerCommissionsPage() {
  const [payouts, setPayouts] = useState<BrokeragePayout[]>([]);
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void partnerPortalService
      .commissions()
      .then((rows) => { if (!cancelled) setPayouts(rows); })
      .catch((err) => { if (!cancelled) toast.error("Could not load commissions", extractErrorMessage(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [toast]);

  const paid = payouts.filter((p) => p.status === "paid").reduce((s, p) => s + Number(p.amount), 0);
  const outstanding = payouts.filter((p) => p.status === "accrued").reduce((s, p) => s + Number(p.amount), 0);

  const columns: DataTableColumn<BrokeragePayout>[] = [
    { key: "when", header: "Accrued", render: (r) => formatDate(r.created_at) },
    {
      key: "amount",
      header: "Brokerage",
      align: "right",
      render: (r) => (
        <div>
          <strong>{formatInr(Number(r.amount))}</strong>
          <div className="muted text-xs">
            {r.rate_type === "percent" ? `${r.rate_snapshot}%` : "flat"}
            {r.deal_value ? ` · deal ${formatInr(Number(r.deal_value))}` : ""}
          </div>
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (r) => <Badge tone={STATUS_TONE[r.status] ?? "neutral"}>{r.status}</Badge>,
    },
    { key: "paid_on", header: "Paid on", render: (r) => (r.paid_on ? formatDate(r.paid_on) : "—") },
  ];

  if (loading) return <LoadingBlock label="Loading commissions…" />;

  return (
    <div>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Commissions</h1>
          <p>Brokerage you have earned from referred deals.</p>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: "var(--space-4)" }}>
        <div className="kpi">
          <div className="kpi__label">Total earned</div>
          <div className="kpi__value">{formatInr(paid + outstanding)}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Paid out</div>
          <div className="kpi__value">{formatInr(paid)}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Outstanding</div>
          <div className="kpi__value">{formatInr(outstanding)}</div>
        </div>
      </div>

      {payouts.length === 0 ? (
        <EmptyState
          title="No commission records yet"
          description="Brokerage is accrued automatically when a lead you referred is marked Sold."
        />
      ) : (
        <Card>
          <DataTable columns={columns} rows={payouts} rowKey={(r) => r.id} />
        </Card>
      )}
    </div>
  );
}
