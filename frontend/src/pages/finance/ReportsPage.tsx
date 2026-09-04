import { useEffect, useState } from "react";

import {
  Button,
  Card,
  DataTable,
  EmptyState,
  LoadingBlock,
  useToast,
  type DataTableColumn
} from "../../components";
import { exportsService } from "../../services/exports";
import { financeService } from "../../services/finance";
import type { FinanceBreakdownRow, FinanceSummary } from "../../types/finance";
import { extractErrorMessage } from "../../utils/errors";
import { formatCurrency } from "../../utils/format";

export default function ReportsPage() {
  const toast = useToast();
  const [summary, setSummary] = useState<FinanceSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      try {
        setSummary(await financeService.getSummary());
      } catch (e) {
        toast.error("Failed to load reports", extractErrorMessage(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function download(fn: () => Promise<void>, label: string) {
    try {
      await fn();
    } catch (e) {
      toast.error(`${label} export failed`, extractErrorMessage(e));
    }
  }

  if (loading) return <LoadingBlock label="Loading reports…" />;
  if (!summary) return <EmptyState title="No finance data yet" />;

  const cols: DataTableColumn<FinanceBreakdownRow>[] = [
    { key: "label", header: "Category", render: (r) => r.label },
    { key: "value", header: "Total", align: "right", render: (r) => formatCurrency(r.value, "INR") }
  ];

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Finance Reports</h1>
          <p>Category summaries and CSV exports.</p>
        </div>
      </div>

      <Card title="Downloads">
        <div className="row" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
          <Button variant="secondary" onClick={() => void download(exportsService.financeExpenses, "Expenses")}>
            Expenses CSV
          </Button>
          <Button variant="secondary" onClick={() => void download(exportsService.financeIncome, "Income")}>
            Income CSV
          </Button>
          <Button variant="secondary" onClick={() => void download(exportsService.vendorBills, "Vendor bills")}>
            Vendor bills CSV
          </Button>
        </div>
      </Card>

      <div className="chart-grid chart-grid--2-1">
        <Card title="Expenses by category">
          <DataTable columns={cols} rows={summary.expense_by_category} rowKey={(r) => r.label} empty={<EmptyState title="No expenses yet" />} />
        </Card>
        <Card title="Income by category">
          <DataTable columns={cols} rows={summary.income_by_category} rowKey={(r) => r.label} empty={<EmptyState title="No income yet" />} />
        </Card>
      </div>
    </>
  );
}
