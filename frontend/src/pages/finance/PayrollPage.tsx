import { useEffect, useState } from "react";

import {
  Button,
  Card,
  DataTable,
  EmptyState,
  KpiCard,
  LoadingBlock,
  TextField,
  useToast,
  type DataTableColumn
} from "../../components";
import { usePermissions } from "../../hooks/usePermissions";
import { financeService } from "../../services/finance";
import type { PayrollEmployee } from "../../types/finance";
import { extractErrorMessage } from "../../utils/errors";
import { formatCurrency } from "../../utils/format";

const thisMonth = () => new Date().toISOString().slice(0, 7);

export default function PayrollPage() {
  const toast = useToast();
  const { has } = usePermissions();
  const canManage = has("FINANCE_SETTINGS_MANAGE");
  const canRun = has("FINANCE_EXPENSE_APPROVE");

  const [employees, setEmployees] = useState<PayrollEmployee[]>([]);
  const [loading, setLoading] = useState(true);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [month, setMonth] = useState(thisMonth());
  const [running, setRunning] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const list = await financeService.listPayrollEmployees();
      setEmployees(list);
      setEdits(Object.fromEntries(list.map((e) => [e.user_id, e.monthly_salary])));
    } catch (e) {
      toast.error("Failed to load payroll", extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refresh();
  }, []);

  async function saveSalary(emp: PayrollEmployee) {
    const val = Number(edits[emp.user_id]);
    if (!(val >= 0)) {
      toast.error("Enter a valid salary");
      return;
    }
    setSavingId(emp.user_id);
    try {
      await financeService.setEmployeeSalary(emp.user_id, val);
      toast.success("Salary updated");
      await refresh();
    } catch (e) {
      toast.error("Save failed", extractErrorMessage(e));
    } finally {
      setSavingId(null);
    }
  }

  async function run() {
    if (!window.confirm(`Run payroll for ${month}? This creates a submitted salary expense per employee.`)) return;
    setRunning(true);
    try {
      const res = await financeService.runPayroll(month);
      toast.success(
        "Payroll run",
        `${res.created} salary expense(s) created, ${res.skipped} skipped · ${formatCurrency(res.total_amount, "INR")}`
      );
    } catch (e) {
      toast.error("Payroll run failed", extractErrorMessage(e));
    } finally {
      setRunning(false);
    }
  }

  const totalSalary = employees.reduce((s, e) => s + Number(e.monthly_salary), 0);

  const columns: DataTableColumn<PayrollEmployee>[] = [
    {
      key: "name",
      header: "Employee",
      render: (e) => (
        <div>
          <strong>{e.name}</strong>
          {e.role ? <div className="muted text-xs">{e.role}</div> : null}
        </div>
      )
    },
    {
      key: "salary",
      header: "Monthly salary",
      align: "right",
      render: (e) =>
        canManage ? (
          <span className="row" style={{ gap: "0.4rem", justifyContent: "flex-end", alignItems: "center" }}>
            <input
              className="input"
              type="number"
              min="0"
              step="0.01"
              style={{ maxWidth: 140 }}
              value={edits[e.user_id] ?? ""}
              onChange={(ev) => setEdits({ ...edits, [e.user_id]: ev.target.value })}
            />
            <Button size="sm" loading={savingId === e.user_id} onClick={() => void saveSalary(e)}>Save</Button>
          </span>
        ) : (
          formatCurrency(e.monthly_salary, "INR")
        )
    }
  ];

  if (loading && employees.length === 0) return <LoadingBlock label="Loading payroll…" />;

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Payroll</h1>
          <p>Set employee salaries and run a month's payroll into finance expenses.</p>
        </div>
      </div>

      <div className="kpi-grid">
        <KpiCard label="Employees" value={String(employees.length)} />
        <KpiCard label="Monthly salary total" value={formatCurrency(totalSalary, "INR")} />
      </div>

      {canRun && (
        <Card title="Run payroll">
          <div className="row" style={{ gap: "0.5rem", alignItems: "flex-end", flexWrap: "wrap" }}>
            <TextField id="pr-month" label="Month" type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
            <Button loading={running} onClick={() => void run()}>Run payroll</Button>
          </div>
          <p className="muted text-sm" style={{ marginTop: "0.5rem" }}>
            Creates one <strong>submitted</strong> salary expense per employee with a salary set — then approve &amp; pay them
            in Expenses. Re-running a month skips employees already generated.
          </p>
        </Card>
      )}

      <Card title="Employees">
        <DataTable
          columns={columns}
          rows={employees}
          rowKey={(e) => e.user_id}
          empty={<EmptyState title="No employees" description="Employee profiles appear here once created in HR." />}
        />
      </Card>
    </>
  );
}
