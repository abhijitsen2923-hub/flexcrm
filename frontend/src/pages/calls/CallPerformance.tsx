import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  KpiCard,
  Modal,
  SkeletonTable,
  useToast,
  type DataTableColumn,
} from "../../components";
import { CHART_AXIS, CHART_GRID, CHART_PALETTE, CHART_PRIMARY } from "../../config/chartTheme";
import { usePermissions } from "../../hooks/usePermissions";
import {
  callsService,
  type CallStatsResponse,
  type CallTrendResponse,
  type EmployeeCallStats,
} from "../../services/callyzer";
import { usersService } from "../../services/users";
import type { User } from "../../types";
import { extractErrorMessage } from "../../utils/errors";
import { formatDateTime } from "../../utils/format";


type RangeKey = "month" | "30" | "7";
const RANGES: { value: RangeKey; label: string }[] = [
  { value: "month", label: "This month" },
  { value: "30", label: "Last 30 days" },
  { value: "7", label: "Last 7 days" },
];

const EMPTY: CallStatsResponse = {
  date_from: "",
  date_to: "",
  totals: { callers: 0, total: 0, connected: 0, missed: 0, total_talk_seconds: 0, unique_clients: 0 },
  rows: [],
};

function rangeToDates(range: RangeKey): { date_from: string; date_to: string } {
  const now = new Date();
  const from =
    range === "month"
      ? new Date(now.getFullYear(), now.getMonth(), 1)
      : new Date(now.getTime() - (range === "30" ? 30 : 7) * 86_400_000);
  return { date_from: from.toISOString(), date_to: now.toISOString() };
}

/** Compact talk-time: "1h 04m" for long spans, else "3m 20s". */
function fmtTalk(seconds: number): string {
  if (!seconds) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`;
  return `${m}m ${String(s).padStart(2, "0")}s`;
}

function ratePct(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

function rateTone(rate: number): "success" | "warning" | "danger" {
  if (rate >= 0.6) return "success";
  if (rate >= 0.3) return "warning";
  return "danger";
}


export default function CallPerformance() {
  const toast = useToast();
  const { has: hasPerm } = usePermissions();
  const canManage = hasPerm("USER_VIEW"); // managers/owner — can assign callers + see the team
  const [range, setRange] = useState<RangeKey>("month");
  const [data, setData] = useState<CallStatsResponse>(EMPTY);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await callsService.stats(rangeToDates(range)));
    } catch (err) {
      toast.error("Couldn't load call performance", extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [range, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  // Users for the "assign caller" picker (managers only).
  const [users, setUsers] = useState<User[]>([]);
  useEffect(() => {
    if (!canManage) return;
    let cancelled = false;
    usersService
      .list({ page_size: 100 })
      .then((res) => { if (!cancelled) setUsers(res.items); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [canManage]);

  // Assign-caller modal.
  const [assignRow, setAssignRow] = useState<EmployeeCallStats | null>(null);
  const [assignUserId, setAssignUserId] = useState("");
  const [assigning, setAssigning] = useState(false);

  async function submitAssign() {
    if (!assignRow?.emp_number || !assignUserId) return;
    setAssigning(true);
    try {
      await callsService.assignAgent({
        emp_number: assignRow.emp_number,
        emp_name: assignRow.name,
        user_id: assignUserId,
      });
      toast.success("Caller assigned", "Past and future calls re-attributed to this user.");
      setAssignRow(null);
      setAssignUserId("");
      await load();
    } catch (err) {
      toast.error("Couldn't assign caller", extractErrorMessage(err));
    } finally {
      setAssigning(false);
    }
  }

  // Per-employee trend drill-down.
  const [trendRow, setTrendRow] = useState<EmployeeCallStats | null>(null);
  const [trend, setTrend] = useState<CallTrendResponse | null>(null);
  const [trendLoading, setTrendLoading] = useState(false);

  useEffect(() => {
    if (!trendRow?.user_id) return;
    let cancelled = false;
    setTrendLoading(true);
    setTrend(null);
    callsService
      .trend(trendRow.user_id, rangeToDates(range))
      .then((res) => { if (!cancelled) setTrend(res); })
      .catch((err) => { if (!cancelled) toast.error("Couldn't load trend", extractErrorMessage(err)); })
      .finally(() => { if (!cancelled) setTrendLoading(false); });
    return () => { cancelled = true; };
  }, [trendRow, range, toast]);

  const totals = data.totals;
  const chartData = useMemo(
    () =>
      data.rows
        .slice(0, 12)
        .map((r) => ({ name: r.name.split(" ")[0] || r.name, calls: r.total, connected: r.connected })),
    [data.rows],
  );

  const columns: DataTableColumn<EmployeeCallStats>[] = [
    {
      key: "employee",
      header: "Employee",
      render: (r) => (
        <div>
          <div style={{ fontWeight: 600 }}>{r.name}</div>
          {r.unmatched ? (
            <span className="muted text-xs">Unmatched · {r.emp_number ?? "—"}</span>
          ) : (
            <span className="muted text-xs" style={{ fontVariantNumeric: "tabular-nums" }}>{r.emp_number ?? "—"}</span>
          )}
        </div>
      ),
    },
    { key: "total", header: "Calls", render: (r) => <span className="cell-nowrap">{r.total}</span> },
    {
      key: "connected",
      header: "Connected",
      render: (r) => (
        <span className="cell-nowrap">
          {r.connected} <Badge tone={rateTone(r.connect_rate)}>{ratePct(r.connect_rate)}</Badge>
        </span>
      ),
    },
    { key: "missed", header: "Missed", render: (r) => <span className="cell-nowrap">{r.missed}</span> },
    { key: "clients", header: "Clients", render: (r) => <span className="cell-nowrap">{r.unique_clients}</span> },
    { key: "talk", header: "Talk time", render: (r) => <span className="cell-nowrap">{fmtTalk(r.total_talk_seconds)}</span> },
    { key: "avg", header: "Avg / call", render: (r) => <span className="cell-nowrap">{fmtTalk(r.avg_talk_seconds)}</span> },
    { key: "last", header: "Last call", render: (r) => (r.last_call_at ? formatDateTime(r.last_call_at) : "—") },
    {
      key: "actions",
      header: "",
      label: "Action", // stacked-card row label on phones (header is blank on desktop)
      align: "right",
      render: (r) =>
        r.unmatched ? (
          canManage && r.emp_number ? (
            <Button size="sm" variant="ghost" onClick={() => { setAssignUserId(""); setAssignRow(r); }}>
              Assign
            </Button>
          ) : null
        ) : (
          <Button size="sm" variant="ghost" onClick={() => setTrendRow(r)}>
            Trend
          </Button>
        ),
    },
  ];

  return (
    <div className="stack" style={{ gap: "1rem" }}>
      <div className="row" style={{ gap: "0.4rem", flexWrap: "wrap" }}>
        {RANGES.map((r) => (
          <button
            key={r.value}
            type="button"
            className={`filter-chip${range === r.value ? " is-active" : ""}`}
            onClick={() => setRange(r.value)}
          >
            {r.label}
          </button>
        ))}
      </div>

      <div className="kpi-grid">
        <KpiCard label="Active callers" value={String(totals.callers)} />
        <KpiCard label="Total calls" value={String(totals.total)} hint={`${totals.unique_clients} unique clients`} />
        <KpiCard
          label="Connected"
          value={String(totals.connected)}
          hint={totals.total ? `${ratePct(totals.connected / totals.total)} connect rate` : undefined}
        />
        <KpiCard label="Talk time" value={fmtTalk(totals.total_talk_seconds)} hint={`${totals.missed} missed`} />
      </div>

      {chartData.length > 0 && (
        <Card title="Calls per employee">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid stroke={CHART_GRID} vertical={false} />
              <XAxis dataKey="name" stroke={CHART_AXIS} tick={{ fontSize: 12 }} interval={0} angle={-20} textAnchor="end" height={50} />
              <YAxis stroke={CHART_AXIS} tick={{ fontSize: 12 }} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="calls" fill={CHART_PRIMARY} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      <div className="table-wrap">
        {loading && data.rows.length === 0 ? (
          <SkeletonTable cols={9} rows={6} />
        ) : (
          <DataTable
            columns={columns}
            rows={data.rows}
            rowKey={(r) => (r.user_id ?? r.emp_number ?? r.name)}
            empty={
              <EmptyState
                title="No call activity"
                description="No calls in this period yet. Once Callyzer syncs, per-employee performance appears here."
              />
            }
          />
        )}
      </div>

      <Modal
        open={!!assignRow}
        title="Assign caller to a user"
        onClose={() => setAssignRow(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setAssignRow(null)}>Cancel</Button>
            <Button onClick={() => void submitAssign()} loading={assigning} disabled={!assignUserId}>Assign</Button>
          </>
        }
      >
        <div className="stack" style={{ gap: "0.75rem" }}>
          <p className="muted text-sm" style={{ margin: 0 }}>
            Map <strong>{assignRow?.emp_number ?? assignRow?.name}</strong>&apos;s calls to a FlexCRM user.
            This re-labels this number&apos;s <strong>past and future</strong> calls, so performance and scorecards update.
          </p>
          <select className="input" value={assignUserId} onChange={(e) => setAssignUserId(e.target.value)} aria-label="User">
            <option value="">Select a user…</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>{u.first_name} {u.last_name}</option>
            ))}
          </select>
        </div>
      </Modal>

      <Modal open={!!trendRow} title={`Call trend · ${trendRow?.name ?? ""}`} onClose={() => setTrendRow(null)} size="lg">
        {trendLoading ? (
          <SkeletonTable cols={2} rows={4} />
        ) : trend && trend.points.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart
              data={trend.points.map((p) => ({ ...p, label: p.date.slice(5) }))}
              margin={{ top: 8, right: 8, bottom: 0, left: -16 }}
            >
              <CartesianGrid stroke={CHART_GRID} vertical={false} />
              <XAxis dataKey="label" stroke={CHART_AXIS} tick={{ fontSize: 12 }} />
              <YAxis stroke={CHART_AXIS} tick={{ fontSize: 12 }} allowDecimals={false} />
              <Tooltip />
              <Line type="monotone" dataKey="calls" stroke={CHART_PRIMARY} strokeWidth={2} dot={false} name="Calls" />
              <Line type="monotone" dataKey="connected" stroke={CHART_PALETTE[2]} strokeWidth={2} dot={false} name="Connected" />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <EmptyState title="No calls" description="No calls for this employee in the selected range." />
        )}
      </Modal>
    </div>
  );
}
