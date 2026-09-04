import { useEffect, useState } from "react";

import {
  Button,
  Card,
  DataTable,
  EmptyState,
  LoadingBlock,
  Modal,
  TextField,
  TextareaField,
  useToast,
  type DataTableColumn
} from "../../components";
import { usePermissions } from "../../hooks/usePermissions";
import { financeService } from "../../services/finance";
import type { Vendor } from "../../types/finance";
import { extractErrorMessage } from "../../utils/errors";

const EMPTY = {
  name: "", contact_name: "", phone: "", email: "", gstin: "", pan: "",
  state_code: "", bank_account: "", ifsc: "", upi: "", address: "", notes: ""
};

export default function VendorsPage() {
  const toast = useToast();
  const { has } = usePermissions();
  const canManage = has("FINANCE_VENDOR_MANAGE");

  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Vendor | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      setVendors(await financeService.listVendors());
    } catch (e) {
      toast.error("Failed to load vendors", extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refresh();
  }, []);

  function openCreate() {
    setEditing(null);
    setForm(EMPTY);
    setModalOpen(true);
  }
  function openEdit(v: Vendor) {
    setEditing(v);
    setForm({
      name: v.name, contact_name: v.contact_name ?? "", phone: v.phone ?? "", email: v.email ?? "",
      gstin: v.gstin ?? "", pan: v.pan ?? "", state_code: v.state_code ?? "", bank_account: v.bank_account ?? "",
      ifsc: v.ifsc ?? "", upi: v.upi ?? "", address: v.address ?? "", notes: v.notes ?? ""
    });
    setModalOpen(true);
  }

  async function save() {
    if (!form.name.trim()) {
      toast.error("Vendor name is required");
      return;
    }
    setSaving(true);
    try {
      if (editing) await financeService.updateVendor(editing.id, form);
      else await financeService.createVendor(form);
      toast.success(editing ? "Vendor updated" : "Vendor created");
      setModalOpen(false);
      await refresh();
    } catch (e) {
      toast.error("Save failed", extractErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  async function remove(v: Vendor) {
    if (!window.confirm(`Deactivate vendor "${v.name}"?`)) return;
    try {
      await financeService.deleteVendor(v.id);
      toast.success("Vendor removed");
      await refresh();
    } catch (e) {
      toast.error("Remove failed", extractErrorMessage(e));
    }
  }

  const columns: DataTableColumn<Vendor>[] = [
    { key: "name", header: "Vendor", render: (v) => <strong>{v.name}</strong> },
    {
      key: "contact",
      header: "Contact",
      render: (v) => (
        <span className="muted text-sm">
          {v.contact_name || "—"}
          {v.phone ? ` · ${v.phone}` : ""}
        </span>
      )
    },
    { key: "gstin", header: "GSTIN", render: (v) => v.gstin || "—" },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (v) =>
        canManage ? (
          <span className="row" style={{ gap: "0.4rem", justifyContent: "flex-end" }}>
            <Button size="sm" variant="ghost" onClick={() => openEdit(v)}>Edit</Button>
            <Button size="sm" variant="ghost" onClick={() => void remove(v)}>Remove</Button>
          </span>
        ) : null
    }
  ];

  if (loading && vendors.length === 0) return <LoadingBlock label="Loading vendors…" />;

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Vendors</h1>
          <p>Suppliers and contractors you record bills and payments against.</p>
        </div>
        {canManage && <Button onClick={openCreate}>Add Vendor</Button>}
      </div>

      <Card>
        <DataTable
          columns={columns}
          rows={vendors}
          rowKey={(v) => v.id}
          empty={<EmptyState title="No vendors yet" description="Add a vendor to record bills and payments." />}
        />
      </Card>

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? "Edit Vendor" : "Add Vendor"}
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button loading={saving} onClick={() => void save()}>Save</Button>
          </>
        }
      >
        <div className="form">
          <TextField id="v-name" label="Vendor name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          <div className="form-grid">
            <TextField id="v-contact" label="Contact name" value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} />
            <TextField id="v-phone" label="Phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            <TextField id="v-email" label="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            <TextField id="v-gstin" label="GSTIN" value={form.gstin} onChange={(e) => setForm({ ...form, gstin: e.target.value })} />
            <TextField id="v-pan" label="PAN" value={form.pan} onChange={(e) => setForm({ ...form, pan: e.target.value })} />
            <TextField id="v-state" label="State code" value={form.state_code} onChange={(e) => setForm({ ...form, state_code: e.target.value })} />
            <TextField id="v-bank" label="Bank account" value={form.bank_account} onChange={(e) => setForm({ ...form, bank_account: e.target.value })} />
            <TextField id="v-ifsc" label="IFSC" value={form.ifsc} onChange={(e) => setForm({ ...form, ifsc: e.target.value })} />
            <TextField id="v-upi" label="UPI" value={form.upi} onChange={(e) => setForm({ ...form, upi: e.target.value })} />
          </div>
          <TextareaField id="v-address" label="Address" rows={2} value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
          <TextareaField id="v-notes" label="Notes" rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </div>
      </Modal>
    </>
  );
}
