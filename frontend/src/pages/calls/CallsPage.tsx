import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  Badge,
  Button,
  DataTable,
  EmptyState,
  Pagination,
  SkeletonTable,
  useToast,
  type DataTableColumn,
} from "../../components";
import { callsService, type CallsListResponse, type ExternalCall } from "../../services/callyzer";
import { extractErrorMessage } from "../../utils/errors";
import { formatDateTime } from "../../utils/format";


type TypeFilter = "" | "Incoming" | "Outgoing" | "Missed";
const TYPE_CHIPS: { value: TypeFilter | "unmatched"; label: string }[] = [
  { value: "", label: "All" },
  { value: "Incoming", label: "Incoming" },
  { value: "Outgoing", label: "Outgoing" },
  { value: "Missed", label: "Missed" },
  { value: "unmatched", label: "Unmatched" },
];

const TYPE_TONE: Record<string, "info" | "warning" | "danger" | "neutral"> = {
  Incoming: "info",
  Outgoing: "warning",
  Missed: "danger",
  Rejected: "danger",
};

function fmtDuration(s: number | null): string {
  if (s == null) return "—";
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}m ${String(sec).padStart(2, "0")}s`;
}

const EMPTY: CallsListResponse = { items: [], pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 } };


export default function CallsPage() {
  const toast = useToast();
  const [data, setData] = useState<CallsListResponse>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState<TypeFilter | "unmatched">("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // Debounce the search box (~300ms); reset to page 1 on a new term.
  useEffect(() => {
    const h = setTimeout(() => { setSearch(searchInput.trim()); setPage(1); }, 300);
    return () => clearTimeout(h);
  }, [searchInput]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await callsService.list({
        call_type: typeFilter && typeFilter !== "unmatched" ? typeFilter : undefined,
        matched: typeFilter === "unmatched" ? false : undefined,
        q: search || undefined,
        page,
        page_size: pageSize,
      });
      setData(res);
    } catch (err) {
      toast.error("Couldn't load calls", extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [typeFilter, search, page, pageSize, toast]);

  useEffect(() => { void load(); }, [load]);

  const columns: DataTableColumn<ExternalCall>[] = [
    {
      key: "client",
      header: "Client",
      render: (c) => (
        <div>
          <div style={{ fontWeight: 600 }}>{c.client_name || "Unknown"}</div>
          <div className="muted text-xs" style={{ fontVariantNumeric: "tabular-nums" }}>{c.client_number ?? "—"}</div>
        </div>
      ),
    },
    { key: "employee", header: "Employee", render: (c) => c.emp_name || c.emp_number || "—" },
    {
      key: "type",
      header: "Type",
      render: (c) =>
        c.call_type ? <Badge tone={TYPE_TONE[c.call_type] ?? "neutral"}>{c.call_type}</Badge> : "—",
    },
    { key: "when", header: "When", render: (c) => (c.call_at ? formatDateTime(c.call_at) : "—") },
    { key: "duration", header: "Duration", render: (c) => <span className="cell-nowrap">{fmtDuration(c.duration_seconds)}</span> },
    { key: "disposition", header: "Disposition", render: (c) => c.crm_status || "—" },
    {
      key: "lead",
      header: "Lead",
      render: (c) =>
        c.lead ? (
          <span title={c.lead.contact_name} style={{ fontWeight: 600 }}>#{c.lead.lead_number}</span>
        ) : (
          <span className="muted">Unmatched</span>
        ),
    },
    {
      key: "recording",
      header: "Recording",
      render: (c) =>
        c.recording_url ? (
          <a className="link" href={c.recording_url} target="_blank" rel="noreferrer">▶ Play</a>
        ) : (
          <span className="muted">—</span>
        ),
    },
  ];

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Calls</h1>
          <p>Synced call activity from Callyzer — matched to leads by phone number.</p>
        </div>
        <div className="page-header__actions">
          <Button variant="secondary" size="sm" icon={<RefreshCw size={14} />} onClick={() => void load()} loading={loading}>
            Refresh
          </Button>
        </div>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="row" style={{ gap: "0.6rem", padding: "1rem 1.25rem", borderBottom: "1px solid var(--color-border)", flexWrap: "wrap", alignItems: "center" }}>
          <input
            className="input"
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search number, client or employee"
            aria-label="Search calls"
            style={{ minWidth: 240, flex: "1 1 240px" }}
          />
          <div className="row" style={{ gap: "0.4rem", flexWrap: "wrap" }}>
            {TYPE_CHIPS.map((chip) => (
              <button
                key={chip.value || "all"}
                type="button"
                className={`filter-chip${typeFilter === chip.value ? " is-active" : ""}`}
                onClick={() => { setTypeFilter(chip.value); setPage(1); }}
              >
                {chip.label}
              </button>
            ))}
          </div>
        </div>

        <div className="table-wrap" style={{ border: "none", borderRadius: 0, boxShadow: "none" }}>
          {loading && data.items.length === 0 ? (
            <SkeletonTable cols={8} rows={8} />
          ) : (
            <DataTable
              columns={columns}
              rows={data.items}
              rowKey={(c) => c.id}
              empty={
                <EmptyState
                  title="No calls yet"
                  description="Once Callyzer syncs, your team's calls will appear here."
                />
              }
            />
          )}
        </div>

        <Pagination
          page={data.pagination.page}
          pageSize={data.pagination.page_size}
          total={data.pagination.total}
          totalPages={data.pagination.total_pages}
          onPageChange={setPage}
          pageSizeOptions={[20, 50, 100]}
          onPageSizeChange={(s) => { setPageSize(s); setPage(1); }}
        />
      </div>
    </>
  );
}
