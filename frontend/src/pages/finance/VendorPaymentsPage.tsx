import { useEffect, useMemo, useState } from "react";

import {
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  LoadingBlock,
  Modal,
  SelectField,
  TextField,
  TextareaField,
  useToast,
  type DataTableColumn
} from "../../components";
import { usePermissions } from "../../hooks/usePermissions";
import { financeService } from "../../services/finance";
import type { GstInput, Vendor, VendorBill, VendorBillStatus } from "../../types/finance";
import { extractErrorMessage } from "../../utils/errors";
import { formatCurrency, formatDate } from "../../utils/format";
import { EMPTY_GST, GstFields } from "./components/GstFields";

const STATUS_TONE: Record<VendorBillStatus, "success" | "warning" | "danger" | "neutral"> = {
  open: "warning",
  partially_paid: "warning",
  paid: "success",
  cancelled: "neutral"
};

export default function VendorPaymentsPage() {
  const toast = useToast();
  const { has } = usePermissions();
  const canManage = has("FINANCE_VENDOR_MANAGE");
  const canPay = has("FINANCE_RECORD_PAYMENT");

  const [bills, setBills] = useState<VendorBill[]>([]);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [loading, setLoading] = useState(true);

  const [billOpen, setBillOpen] = useState(false);
  const [billForm, setBillForm] = useState({ vendor_id: "", vendor_invoice_no: "", bill_date: "", due_date: "", description: "" });
  const [billGst, setBillGst] = useState<GstInput>(EMPTY_GST);
  const [savingBill, setSavingBill] = useState(false);

  const [payBill, setPayBill] = useState<VendorBill | null>(null);
  const [payForm, setPayForm] = useState({ amount: "", paid_on: "", method: "", txn_ref: "", note: "" });
  const [savingPay, setSavingPay] = useState(false);

  const vendorName = useMemo(() => new Map(vendors.map((v) => [v.id, v.name])), [vendors]);

  async function refresh() {
    setLoading(true);
    try {
      const [b, v] = await Promise.all([financeService.listVendorBills(), financeService.listVendors()]);
      setBills(b);
      setVendors(v);
    } catch (e) {
      toast.error("Failed to load vendor bills", extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refresh();
  }, []);

  const outstanding = (b: VendorBill) => Number(b.net_payable) - Number(b.amount_paid);

  async function createBill() {
    if (!billForm.vendor_id) {
      toast.error("Please pick a vendor");
      return;
    }
    setSavingBill(true);
    try {
      await financeService.createVendorBill({
        ...billGst,
        vendor_id: billForm.vendor_id,
        vendor_invoice_no: billForm.vendor_invoice_no || null,
        bill_date: billForm.bill_date || null,
        due_date: billForm.due_date || null,
        description: billForm.description || null
      });
      toast.success("Bill created");
      setBillOpen(false);
      setBillForm({ vendor_id: "", vendor_invoice_no: "", bill_date: "", due_date: "", description: "" });
      setBillGst(EMPTY_GST);
      await refresh();
    } catch (e) {
      toast.error("Create failed", extractErrorMessage(e));
    } finally {
      setSavingBill(false);
    }
  }

  function openPay(b: VendorBill) {
    setPayBill(b);
    setPayForm({
      amount: String(outstanding(b)),
      paid_on: new Date().toISOString().slice(0, 10),
      method: "",
      txn_ref: "",
      note: ""
    });
  }

  async function recordPayment() {
    if (!payBill) return;
    const amt = Number(payForm.amount);
    if (!(amt > 0)) {
      toast.error("Enter a valid amount");
      return;
    }
    setSavingPay(true);
    try {
      await financeService.recordVendorPayment(payBill.id, {
        amount: amt,
        paid_on: payForm.paid_on,
        method: payForm.method || undefined,
        txn_ref: payForm.txn_ref || undefined,
        note: payForm.note || undefined
      });
      toast.success("Payment recorded");
      setPayBill(null);
      await refresh();
    } catch (e) {
      toast.error("Payment failed", extractErrorMessage(e));
    } finally {
      setSavingPay(false);
    }
  }

  async function cancelBill(b: VendorBill) {
    if (!window.confirm(`Cancel bill ${b.bill_number}?`)) return;
    try {
      await financeService.cancelVendorBill(b.id);
      toast.success("Bill cancelled");
      await refresh();
    } catch (e) {
      toast.error("Cancel failed", extractErrorMessage(e));
    }
  }

  const columns: DataTableColumn<VendorBill>[] = [
    {
      key: "bill",
      header: "Bill",
      render: (b) => (
        <div>
          <strong>{b.bill_number}</strong>
          <div className="muted text-xs">
            {vendorName.get(b.vendor_id) ?? "—"}
            {b.vendor_invoice_no ? ` · ${b.vendor_invoice_no}` : ""}
          </div>
        </div>
      )
    },
    { key: "due", header: "Due", render: (b) => formatDate(b.due_date) },
    { key: "payable", header: "Payable", align: "right", render: (b) => formatCurrency(b.net_payable, "INR") },
    { key: "paid", header: "Paid", align: "right", render: (b) => formatCurrency(b.amount_paid, "INR") },
    { key: "outstanding", header: "Outstanding", align: "right", render: (b) => <strong>{formatCurrency(outstanding(b), "INR")}</strong> },
    { key: "status", header: "Status", render: (b) => <Badge tone={STATUS_TONE[b.status]}>{b.status.replace("_", " ")}</Badge> },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (b) => (
        <span className="row" style={{ gap: "0.4rem", justifyContent: "flex-end" }}>
          {canPay && b.status !== "paid" && b.status !== "cancelled" && (
            <Button size="sm" onClick={() => openPay(b)}>Pay</Button>
          )}
          {canManage && b.status !== "paid" && b.status !== "cancelled" && (
            <Button size="sm" variant="ghost" onClick={() => void cancelBill(b)}>Cancel</Button>
          )}
        </span>
      )
    }
  ];

  if (loading && bills.length === 0) return <LoadingBlock label="Loading vendor payments…" />;

  const vendorOptions = vendors.map((v) => ({ value: v.id, label: v.name }));

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Vendor Payments</h1>
          <p>Vendor bills (accounts payable) and the payments against them.</p>
        </div>
        {canManage && <Button onClick={() => setBillOpen(true)}>Add Bill</Button>}
      </div>

      <Card>
        <DataTable
          columns={columns}
          rows={bills}
          rowKey={(b) => b.id}
          empty={<EmptyState title="No vendor bills yet" description="Add a bill to track what you owe a vendor." />}
        />
      </Card>

      <Modal
        open={billOpen}
        onClose={() => setBillOpen(false)}
        title="Add Vendor Bill"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setBillOpen(false)}>Cancel</Button>
            <Button loading={savingBill} onClick={() => void createBill()}>Save Bill</Button>
          </>
        }
      >
        <div className="form">
          <div className="form-grid">
            <SelectField
              id="b-vendor"
              label="Vendor"
              value={billForm.vendor_id}
              onChange={(e) => setBillForm({ ...billForm, vendor_id: e.target.value })}
              options={vendorOptions}
              placeholder="Select a vendor…"
            />
            <TextField id="b-inv" label="Vendor invoice #" value={billForm.vendor_invoice_no} onChange={(e) => setBillForm({ ...billForm, vendor_invoice_no: e.target.value })} />
            <TextField id="b-date" label="Bill date" type="date" value={billForm.bill_date} onChange={(e) => setBillForm({ ...billForm, bill_date: e.target.value })} />
            <TextField id="b-due" label="Due date" type="date" value={billForm.due_date} onChange={(e) => setBillForm({ ...billForm, due_date: e.target.value })} />
          </div>
          <GstFields value={billGst} onChange={setBillGst} />
          <TextareaField id="b-desc" label="Description" rows={2} value={billForm.description} onChange={(e) => setBillForm({ ...billForm, description: e.target.value })} />
        </div>
      </Modal>

      <Modal
        open={payBill !== null}
        onClose={() => setPayBill(null)}
        title={payBill ? `Pay ${payBill.bill_number}` : "Pay"}
        footer={
          <>
            <Button variant="secondary" onClick={() => setPayBill(null)}>Cancel</Button>
            <Button loading={savingPay} onClick={() => void recordPayment()}>Record Payment</Button>
          </>
        }
      >
        {payBill && (
          <div className="form">
            <div className="muted text-sm">
              Outstanding: <strong>{formatCurrency(outstanding(payBill), "INR")}</strong>
            </div>
            <div className="form-grid">
              <TextField id="p-amount" label="Amount (₹)" type="number" min="0" step="0.01" value={payForm.amount} onChange={(e) => setPayForm({ ...payForm, amount: e.target.value })} required />
              <TextField id="p-date" label="Paid on" type="date" value={payForm.paid_on} onChange={(e) => setPayForm({ ...payForm, paid_on: e.target.value })} required />
              <TextField id="p-method" label="Method" value={payForm.method} onChange={(e) => setPayForm({ ...payForm, method: e.target.value })} />
              <TextField id="p-ref" label="Txn reference" value={payForm.txn_ref} onChange={(e) => setPayForm({ ...payForm, txn_ref: e.target.value })} />
            </div>
            <TextField id="p-note" label="Note" value={payForm.note} onChange={(e) => setPayForm({ ...payForm, note: e.target.value })} />
          </div>
        )}
      </Modal>
    </>
  );
}
