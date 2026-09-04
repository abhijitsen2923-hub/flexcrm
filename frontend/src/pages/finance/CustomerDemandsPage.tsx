import { useEffect, useMemo, useState } from "react";

import {
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  KpiCard,
  LoadingBlock,
  Modal,
  SelectField,
  TextField,
  TextareaField,
  useToast,
  type DataTableColumn
} from "../../components";
import { usePermissions } from "../../hooks/usePermissions";
import { customersService } from "../../services/customers";
import { financeService } from "../../services/finance";
import type { CustomerContract, CustomerContractListItem, CustomerDemand } from "../../types/finance";
import { extractErrorMessage } from "../../utils/errors";
import { formatCurrency, formatDate } from "../../utils/format";

type Tone = "success" | "warning" | "danger" | "neutral" | "info";
const DEMAND_TONE: Record<string, Tone> = {
  open: "warning",
  partially_paid: "warning",
  paid: "success",
  cancelled: "neutral"
};

const today = () => new Date().toISOString().slice(0, 10);

export default function CustomerDemandsPage() {
  const toast = useToast();
  const { has } = usePermissions();
  const canManage = has("FINANCE_RECORD_PAYMENT");

  const [contracts, setContracts] = useState<CustomerContractListItem[]>([]);
  const [customers, setCustomers] = useState<{ id: string; label: string }[]>([]);
  const [loading, setLoading] = useState(true);

  // create contract
  const [contractOpen, setContractOpen] = useState(false);
  const [contractForm, setContractForm] = useState({ customer_id: "", title: "", contract_value: "", notes: "" });
  const [savingContract, setSavingContract] = useState(false);

  // contract detail
  const [detail, setDetail] = useState<CustomerContract | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [demandForm, setDemandForm] = useState({ description: "", amount: "", due_date: "" });
  const [busy, setBusy] = useState(false);
  const [receiveFor, setReceiveFor] = useState<CustomerDemand | null>(null);
  const [receiveForm, setReceiveForm] = useState({ amount: "", received_on: today(), method: "", txn_ref: "" });

  const customerName = useMemo(() => new Map(customers.map((c) => [c.id, c.label])), [customers]);

  async function refresh() {
    setLoading(true);
    try {
      const [cons, custRes] = await Promise.all([
        financeService.listContracts(),
        customersService.list({ page_size: 200 })
      ]);
      setContracts(cons);
      setCustomers(custRes.items.map((c) => ({ id: c.id, label: c.company_name || c.contact_name })));
    } catch (e) {
      toast.error("Failed to load contracts", extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refresh();
  }, []);

  async function openDetail(id: string) {
    setDetailLoading(true);
    setDemandForm({ description: "", amount: "", due_date: "" });
    setReceiveFor(null);
    try {
      setDetail(await financeService.getContract(id));
    } catch (e) {
      toast.error("Failed to load contract", extractErrorMessage(e));
    } finally {
      setDetailLoading(false);
    }
  }

  async function reloadDetail() {
    if (!detail) return;
    setDetail(await financeService.getContract(detail.id));
    setContracts(await financeService.listContracts());
  }

  async function createContract() {
    if (!contractForm.customer_id || !contractForm.title.trim() || !contractForm.contract_value) {
      toast.error("Customer, title and contract value are required");
      return;
    }
    setSavingContract(true);
    try {
      await financeService.createContract({
        customer_id: contractForm.customer_id,
        title: contractForm.title,
        contract_value: Number(contractForm.contract_value),
        notes: contractForm.notes || null
      });
      toast.success("Contract created");
      setContractOpen(false);
      setContractForm({ customer_id: "", title: "", contract_value: "", notes: "" });
      await refresh();
    } catch (e) {
      toast.error("Create failed", extractErrorMessage(e));
    } finally {
      setSavingContract(false);
    }
  }

  async function raiseDemand() {
    if (!detail) return;
    const amt = Number(demandForm.amount);
    if (!(amt > 0)) {
      toast.error("Enter a demand amount");
      return;
    }
    setBusy(true);
    try {
      await financeService.raiseDemand(detail.id, {
        description: demandForm.description || null,
        amount: amt,
        due_date: demandForm.due_date || null
      });
      setDemandForm({ description: "", amount: "", due_date: "" });
      await reloadDetail();
      toast.success("Demand raised");
    } catch (e) {
      toast.error("Failed to raise demand", extractErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function openReceive(d: CustomerDemand) {
    setReceiveFor(d);
    setReceiveForm({ amount: String(Number(d.outstanding)), received_on: today(), method: "", txn_ref: "" });
  }

  async function recordReceipt() {
    if (!receiveFor) return;
    const amt = Number(receiveForm.amount);
    if (!(amt > 0)) {
      toast.error("Enter an amount");
      return;
    }
    setBusy(true);
    try {
      await financeService.recordDemandReceipt(receiveFor.id, {
        amount: amt,
        received_on: receiveForm.received_on,
        method: receiveForm.method || undefined,
        txn_ref: receiveForm.txn_ref || undefined
      });
      setReceiveFor(null);
      await reloadDetail();
      toast.success("Receipt recorded");
    } catch (e) {
      toast.error("Failed to record receipt", extractErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function cancelDemand(d: CustomerDemand) {
    if (!window.confirm(`Cancel demand ${d.demand_number}?`)) return;
    setBusy(true);
    try {
      await financeService.cancelDemand(d.id);
      await reloadDetail();
      toast.success("Demand cancelled");
    } catch (e) {
      toast.error("Cancel failed", extractErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const columns: DataTableColumn<CustomerContractListItem>[] = [
    {
      key: "contract",
      header: "Contract",
      render: (c) => (
        <div>
          <strong>{c.title}</strong>
          <div className="muted text-xs">{customerName.get(c.customer_id) ?? "—"}</div>
        </div>
      )
    },
    { key: "value", header: "Contract value", align: "right", render: (c) => formatCurrency(c.contract_value, "INR") },
    { key: "received", header: "Received", align: "right", render: (c) => formatCurrency(c.total_received, "INR") },
    { key: "balance", header: "Balance", align: "right", render: (c) => <strong>{formatCurrency(c.balance, "INR")}</strong> },
    { key: "status", header: "Status", render: (c) => <Badge tone={c.status === "closed" ? "neutral" : "info"}>{c.status}</Badge> }
  ];

  if (loading && contracts.length === 0) return <LoadingBlock label="Loading contracts…" />;

  const demandColumns: DataTableColumn<CustomerDemand>[] = [
    {
      key: "demand",
      header: "Demand",
      render: (d) => (
        <div>
          <strong>{d.demand_number}</strong>
          {d.description ? <div className="muted text-xs">{d.description}</div> : null}
        </div>
      )
    },
    { key: "due", header: "Due", render: (d) => formatDate(d.due_date) },
    { key: "amount", header: "Amount", align: "right", render: (d) => formatCurrency(d.amount, "INR") },
    { key: "received", header: "Received", align: "right", render: (d) => formatCurrency(d.amount_received, "INR") },
    { key: "outstanding", header: "Outstanding", align: "right", render: (d) => <strong>{formatCurrency(d.outstanding, "INR")}</strong> },
    { key: "status", header: "Status", render: (d) => <Badge tone={DEMAND_TONE[d.status] ?? "neutral"}>{d.status.replace("_", " ")}</Badge> },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (d) =>
        canManage && d.status !== "paid" && d.status !== "cancelled" ? (
          <span className="row" style={{ gap: "0.4rem", justifyContent: "flex-end" }}>
            <Button size="sm" onClick={() => openReceive(d)}>Receive</Button>
            {Number(d.amount_received) === 0 && (
              <Button size="sm" variant="ghost" onClick={() => void cancelDemand(d)}>Cancel</Button>
            )}
          </span>
        ) : null
    }
  ];

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Customer Demands</h1>
          <p>Per-customer contract → raise demands of any amount → receipts reduce the balance.</p>
        </div>
        {canManage && <Button onClick={() => setContractOpen(true)}>New Contract</Button>}
      </div>

      <Card>
        <DataTable
          columns={columns}
          rows={contracts}
          rowKey={(c) => c.id}
          onRowClick={(c) => void openDetail(c.id)}
          empty={<EmptyState title="No contracts yet" description="Create a customer contract, then raise demands against it." />}
        />
      </Card>

      {/* New contract */}
      <Modal
        open={contractOpen}
        onClose={() => setContractOpen(false)}
        title="New Customer Contract"
        footer={
          <>
            <Button variant="secondary" onClick={() => setContractOpen(false)}>Cancel</Button>
            <Button loading={savingContract} onClick={() => void createContract()}>Create</Button>
          </>
        }
      >
        <div className="form">
          <SelectField
            id="c-customer"
            label="Customer"
            value={contractForm.customer_id}
            onChange={(e) => setContractForm({ ...contractForm, customer_id: e.target.value })}
            options={customers.map((c) => ({ value: c.id, label: c.label }))}
            placeholder="Select a customer…"
          />
          <TextField id="c-title" label="Contract title" value={contractForm.title} onChange={(e) => setContractForm({ ...contractForm, title: e.target.value })} required />
          <TextField id="c-value" label="Contract value (₹)" type="number" min="0" step="0.01" value={contractForm.contract_value} onChange={(e) => setContractForm({ ...contractForm, contract_value: e.target.value })} required />
          <TextareaField id="c-notes" label="Notes" rows={2} value={contractForm.notes} onChange={(e) => setContractForm({ ...contractForm, notes: e.target.value })} />
        </div>
      </Modal>

      {/* Contract detail */}
      <Modal
        open={detail !== null}
        onClose={() => setDetail(null)}
        size="lg"
        title={detail ? detail.title : "Contract"}
        footer={<Button variant="secondary" onClick={() => setDetail(null)}>Close</Button>}
      >
        {detailLoading || !detail ? (
          <LoadingBlock label="Loading…" />
        ) : (
          <div className="stack" style={{ gap: "1rem" }}>
            <div className="kpi-grid">
              <KpiCard label="Contract value" value={formatCurrency(detail.contract_value, "INR")} />
              <KpiCard label="Demanded" value={formatCurrency(detail.total_demanded, "INR")} />
              <KpiCard label="Received" value={formatCurrency(detail.total_received, "INR")} />
              <KpiCard label="Balance" value={formatCurrency(detail.balance, "INR")} />
            </div>

            {canManage && detail.status !== "closed" && (
              <Card title="Raise a demand">
                <div className="form-grid">
                  <TextField id="d-amount" label="Amount (₹)" type="number" min="0" step="0.01" value={demandForm.amount} onChange={(e) => setDemandForm({ ...demandForm, amount: e.target.value })} />
                  <TextField id="d-due" label="Due date (optional)" type="date" value={demandForm.due_date} onChange={(e) => setDemandForm({ ...demandForm, due_date: e.target.value })} />
                  <TextField id="d-desc" label="Description (optional)" value={demandForm.description} onChange={(e) => setDemandForm({ ...demandForm, description: e.target.value })} />
                </div>
                <div style={{ marginTop: "0.5rem" }}>
                  <Button size="sm" loading={busy} onClick={() => void raiseDemand()}>Raise demand</Button>
                </div>
              </Card>
            )}

            <DataTable
              columns={demandColumns}
              rows={detail.demands}
              rowKey={(d) => d.id}
              empty={<EmptyState title="No demands yet" description="Raise a demand above." />}
            />

            {receiveFor && (
              <Card title={`Record receipt · ${receiveFor.demand_number}`}>
                <div className="form-grid">
                  <TextField id="r-amount" label="Amount (₹)" type="number" min="0" step="0.01" value={receiveForm.amount} onChange={(e) => setReceiveForm({ ...receiveForm, amount: e.target.value })} required />
                  <TextField id="r-date" label="Received on" type="date" value={receiveForm.received_on} onChange={(e) => setReceiveForm({ ...receiveForm, received_on: e.target.value })} required />
                  <TextField id="r-method" label="Method" value={receiveForm.method} onChange={(e) => setReceiveForm({ ...receiveForm, method: e.target.value })} />
                  <TextField id="r-ref" label="Txn reference" value={receiveForm.txn_ref} onChange={(e) => setReceiveForm({ ...receiveForm, txn_ref: e.target.value })} />
                </div>
                <div className="row" style={{ gap: "0.4rem", marginTop: "0.5rem" }}>
                  <Button size="sm" variant="secondary" onClick={() => setReceiveFor(null)}>Cancel</Button>
                  <Button size="sm" loading={busy} onClick={() => void recordReceipt()}>Save receipt</Button>
                </div>
              </Card>
            )}
          </div>
        )}
      </Modal>
    </>
  );
}
