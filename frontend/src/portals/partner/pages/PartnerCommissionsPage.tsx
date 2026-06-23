import { useEffect, useState } from "react";
import { Badge, Card, DataTable, EmptyState, LoadingBlock, useToast, type DataTableColumn } from "../../../components";
import { useAuth } from "../../../hooks/useAuth";
import { financeService } from "../../../services/finance";
import { extractErrorMessage } from "../../../utils/errors";
import { formatCurrency, formatDateTime } from "../../../utils/format";
import type { CommissionLedgerEntry } from "../../../types";

export default function PartnerCommissionsPage() {
  const { user } = useAuth();
  const [entries, setEntries] = useState<CommissionLedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void financeService
      .listLedger(user?.id)
      .then((rows) => { if (!cancelled) setEntries(rows); })
      .catch((err) => {
        if (!cancelled) toast.error("Could not load commissions", extractErrorMessage(err));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [user?.id, toast]);

  const total = entries
    .filter((e) => e.direction === "payable")
    .reduce((sum, e) => sum + Number(e.amount), 0);

  const paid = entries
    .filter((e) => e.direction === "paid")
    .reduce((sum, e) => sum + Number(e.amount), 0);

  const columns: DataTableColumn<CommissionLedgerEntry>[] = [
    { key: "when", header: "Date", render: (row) => formatDateTime(row.recorded_at) },
    {
      key: "dir",
      header: "Type",
      render: (row) => (
        <Badge
          tone={
            row.direction === "reversed"
              ? "danger"
              : row.direction === "paid"
                ? "success"
                : "info"
          }
        >
          {row.direction}
        </Badge>
      ),
    },
    {
      key: "amount",
      header: "Amount",
      align: "right",
      render: (row) => formatCurrency(row.amount),
    },
    { key: "note", header: "Note", render: (row) => row.note ?? "—" },
  ];

  if (loading) return <LoadingBlock label="Loading commissions…" />;

  return (
    <div>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Commissions</h1>
          <p>Your earned commissions from referred bookings.</p>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: "var(--space-4)" }}>
        <div className="kpi">
          <div className="kpi__label">Total payable</div>
          <div className="kpi__value">{formatCurrency(total)}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Paid out</div>
          <div className="kpi__value">{formatCurrency(paid)}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Outstanding</div>
          <div className="kpi__value">{formatCurrency(total - paid)}</div>
        </div>
      </div>

      {entries.length === 0 ? (
        <EmptyState
          title="No commission records yet"
          description="Commission entries appear here when a booking linked to your referral is confirmed."
        />
      ) : (
        <Card>
          <DataTable columns={columns} rows={entries} rowKey={(r) => r.id} />
        </Card>
      )}
    </div>
  );
}
