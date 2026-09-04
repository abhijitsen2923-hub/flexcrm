import { useEffect, useState } from "react";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { Card, EmptyState, KpiCard, LoadingBlock, useToast } from "../../components";
import { CHART_PALETTE } from "../../config/chartTheme";
import { financeService } from "../../services/finance";
import type { FinanceSummary } from "../../types/finance";
import { extractErrorMessage } from "../../utils/errors";
import { formatCurrency } from "../../utils/format";

export default function FinanceDashboardPage() {
  const toast = useToast();
  const [summary, setSummary] = useState<FinanceSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      try {
        setSummary(await financeService.getSummary());
      } catch (e) {
        toast.error("Failed to load finance dashboard", extractErrorMessage(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <LoadingBlock label="Loading finance dashboard…" />;
  if (!summary) return <EmptyState title="No finance data yet" />;

  const expenseData = summary.expense_by_category
    .map((r) => ({ label: r.label, value: Number(r.value) }))
    .filter((r) => r.value > 0);

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Finance Dashboard</h1>
          <p>Income, expenses, payables and GST at a glance.</p>
        </div>
      </div>

      <div className="kpi-grid">
        <KpiCard
          label="Total income"
          value={formatCurrency(summary.income_total, "INR")}
          hint={`Sales ${formatCurrency(summary.sales_revenue_total, "INR")} · Manual ${formatCurrency(summary.manual_income_total, "INR")}`}
        />
        <KpiCard label="Total expenses" value={formatCurrency(summary.expense_total, "INR")} />
        <KpiCard label="Paid out" value={formatCurrency(summary.expense_paid, "INR")} />
        <KpiCard label="Vendor payable" value={formatCurrency(summary.vendor_payable_outstanding, "INR")} />
        <KpiCard label="Net (income − paid)" value={formatCurrency(summary.net_position, "INR")} />
        <KpiCard
          label="Net GST"
          value={formatCurrency(summary.net_gst, "INR")}
          hint={`Output ${formatCurrency(summary.output_gst, "INR")} · Input ${formatCurrency(summary.input_gst, "INR")}`}
        />
        <KpiCard label="Pending approvals" value={String(summary.expense_pending_approval)} />
      </div>

      <Card title="Expenses by category">
        {expenseData.length === 0 ? (
          <EmptyState title="No expenses yet" />
        ) : (
          <div style={{ height: 300 }}>
            <ResponsiveContainer>
              <PieChart>
                <Pie data={expenseData} dataKey="value" nameKey="label" innerRadius={60} outerRadius={100} isAnimationActive={false}>
                  {expenseData.map((_, i) => (
                    <Cell key={i} fill={CHART_PALETTE[i % CHART_PALETTE.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>
    </>
  );
}
