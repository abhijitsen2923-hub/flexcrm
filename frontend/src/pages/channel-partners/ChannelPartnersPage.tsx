import { useEffect, useState } from "react";
import { Handshake, Plus } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  Modal,
  SelectField,
  TextField,
  useToast,
  type DataTableColumn,
} from "../../components";
import { LoadingBlock } from "../../components/ui/Spinner";
import { usePermissions } from "../../hooks/usePermissions";
import { channelPartnersService } from "../../services/channelPartners";
import { usersService } from "../../services/users";
import { extractErrorMessage } from "../../utils/errors";
import { formatDate, formatInr } from "../../utils/format";
import type { Lead, User } from "../../types";
import type {
  BrokeragePayout,
  BrokerageType,
  ChannelPartner,
  ChannelPartnerListItem,
} from "../../types/partner";

interface PartnerForm {
  company_name: string;
  contact_name: string;
  phone: string;
  email: string;
  rera_number: string;
  pan: string;
  brokerage_type: BrokerageType;
  brokerage_rate: string;
  payout_bank_account: string;
  payout_ifsc: string;
  payout_upi: string;
  is_active: boolean;
  user_id: string;
}

const BLANK: PartnerForm = {
  company_name: "",
  contact_name: "",
  phone: "",
  email: "",
  rera_number: "",
  pan: "",
  brokerage_type: "percent",
  brokerage_rate: "0",
  payout_bank_account: "",
  payout_ifsc: "",
  payout_upi: "",
  is_active: true,
  user_id: "",
};

export default function ChannelPartnersPage() {
  const toast = useToast();
  const { has } = usePermissions();
  const canManage = has("USER_MANAGE");
  const canPayout = has("FINANCE_RECORD_PAYMENT");

  const [partners, setPartners] = useState<ChannelPartnerListItem[]>([]);
  const [brokerUsers, setBrokerUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);

  // Create/edit modal.
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<PartnerForm>(BLANK);
  const [saving, setSaving] = useState(false);

  // Detail modal.
  const [detail, setDetail] = useState<{ partner: ChannelPartnerListItem; leads: Lead[]; payouts: BrokeragePayout[] } | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const rows = await channelPartnersService.list();
      setPartners(rows);
    } catch (err) {
      toast.error("Could not load channel partners", extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // Broker logins available to link a profile to.
    void usersService
      .list({ role: "broker", page_size: 100 })
      .then((res) => setBrokerUsers(res.items))
      .catch(() => setBrokerUsers([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function set<K extends keyof PartnerForm>(key: K, val: PartnerForm[K]) {
    setForm((prev) => ({ ...prev, [key]: val }));
  }

  function openCreate() {
    setEditingId(null);
    setForm(BLANK);
    setFormOpen(true);
  }

  function openEdit(p: ChannelPartner) {
    setEditingId(p.id);
    setForm({
      company_name: p.company_name,
      contact_name: p.contact_name,
      phone: p.phone ?? "",
      email: p.email ?? "",
      rera_number: p.rera_number ?? "",
      pan: p.pan ?? "",
      brokerage_type: p.brokerage_type,
      brokerage_rate: String(p.brokerage_rate ?? "0"),
      payout_bank_account: p.payout_bank_account ?? "",
      payout_ifsc: p.payout_ifsc ?? "",
      payout_upi: p.payout_upi ?? "",
      is_active: p.is_active,
      user_id: p.user_id ?? "",
    });
    setFormOpen(true);
  }

  async function submitForm() {
    if (!form.company_name.trim() || !form.contact_name.trim()) {
      toast.error("Company and contact name are required");
      return;
    }
    setSaving(true);
    const payload = {
      company_name: form.company_name.trim(),
      contact_name: form.contact_name.trim(),
      phone: form.phone.trim() || null,
      email: form.email.trim() || null,
      rera_number: form.rera_number.trim() || null,
      pan: form.pan.trim() || null,
      brokerage_type: form.brokerage_type,
      brokerage_rate: Number(form.brokerage_rate) || 0,
      payout_bank_account: form.payout_bank_account.trim() || null,
      payout_ifsc: form.payout_ifsc.trim() || null,
      payout_upi: form.payout_upi.trim() || null,
      is_active: form.is_active,
      user_id: form.user_id || null,
    };
    try {
      if (editingId) {
        await channelPartnersService.update(editingId, payload);
        toast.success("Partner updated");
      } else {
        await channelPartnersService.create(payload);
        toast.success("Partner added");
      }
      setFormOpen(false);
      void load();
    } catch (err) {
      toast.error("Could not save partner", extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function openDetail(p: ChannelPartnerListItem) {
    setDetail({ partner: p, leads: [], payouts: [] });
    setDetailLoading(true);
    try {
      const [leads, payouts] = await Promise.all([
        channelPartnersService.leads(p.id),
        canPayout ? channelPartnersService.payouts(p.id) : Promise.resolve([] as BrokeragePayout[]),
      ]);
      setDetail({ partner: p, leads, payouts });
    } catch (err) {
      toast.error("Could not load partner detail", extractErrorMessage(err));
    } finally {
      setDetailLoading(false);
    }
  }

  async function markPaid(payout: BrokeragePayout) {
    if (!detail) return;
    try {
      await channelPartnersService.updatePayout(payout.id, {
        status: "paid",
        paid_on: new Date().toISOString().slice(0, 10),
      });
      toast.success("Marked paid", formatInr(Number(payout.amount)));
      // Refresh the detail payouts + roster (outstanding totals change).
      const payouts = await channelPartnersService.payouts(detail.partner.id);
      setDetail({ ...detail, payouts });
      void load();
    } catch (err) {
      toast.error("Could not update payout", extractErrorMessage(err));
    }
  }

  const columns: DataTableColumn<ChannelPartnerListItem>[] = [
    {
      key: "partner",
      header: "Partner",
      render: (p) => (
        <div>
          <div style={{ fontWeight: 600 }}>{p.company_name}</div>
          <div className="muted text-xs">{p.contact_name}{p.rera_number ? ` · RERA ${p.rera_number}` : ""}</div>
        </div>
      ),
    },
    {
      key: "brokerage",
      header: "Brokerage",
      render: (p) => (p.brokerage_type === "percent" ? `${p.brokerage_rate}%` : formatInr(Number(p.brokerage_rate))),
    },
    { key: "leads", header: "Referred", align: "right", render: (p) => p.stats.leads_total },
    {
      key: "sold",
      header: "Sold",
      align: "right",
      render: (p) => `${p.stats.leads_sold} (${Math.round((p.stats.conversion_rate || 0) * 100)}%)`,
    },
    {
      key: "outstanding",
      header: "Outstanding",
      align: "right",
      render: (p) => formatInr(Number(p.stats.brokerage_outstanding)),
    },
    {
      key: "status",
      header: "Status",
      render: (p) => <Badge tone={p.is_active ? "success" : "neutral"}>{p.is_active ? "Active" : "Inactive"}</Badge>,
    },
    ...(canManage
      ? [{
          key: "actions",
          header: "",
          render: (p: ChannelPartnerListItem) => (
            <Button
              size="sm"
              variant="ghost"
              onClick={(e) => { e.stopPropagation(); openEdit(p); }}
            >
              Edit
            </Button>
          ),
        } as DataTableColumn<ChannelPartnerListItem>]
      : []),
  ];

  if (loading) return <LoadingBlock label="Loading channel partners…" />;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Channel Partners</h1>
        {canManage && (
          <Button variant="primary" icon={<Plus size={16} />} onClick={openCreate}>
            New Partner
          </Button>
        )}
      </div>

      {partners.length === 0 ? (
        <EmptyState
          icon={<Handshake size={32} />}
          title="No channel partners yet"
          description="Add a broker/channel partner to start attributing referrals and brokerage."
        />
      ) : (
        <Card>
          <DataTable columns={columns} rows={partners} rowKey={(p) => p.id} onRowClick={(p) => void openDetail(p)} />
        </Card>
      )}

      {/* Create / edit */}
      {formOpen && (
        <Modal
          open
          title={editingId ? "Edit partner" : "New channel partner"}
          size="lg"
          onClose={() => setFormOpen(false)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setFormOpen(false)} disabled={saving}>Cancel</Button>
              <Button variant="primary" loading={saving} onClick={() => void submitForm()}>
                {editingId ? "Save" : "Add partner"}
              </Button>
            </>
          }
        >
          <div className="stack" style={{ gap: "0.75rem" }}>
            <div className="form-grid">
              <TextField id="cp-company" label="Company / agency" value={form.company_name} onChange={(e) => set("company_name", e.target.value)} required />
              <TextField id="cp-contact" label="Contact name" value={form.contact_name} onChange={(e) => set("contact_name", e.target.value)} required />
            </div>
            <div className="form-grid">
              <TextField id="cp-phone" label="Phone" value={form.phone} onChange={(e) => set("phone", e.target.value)} />
              <TextField id="cp-email" label="Email" type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
            </div>
            <div className="form-grid">
              <TextField id="cp-rera" label="RERA number" value={form.rera_number} onChange={(e) => set("rera_number", e.target.value)} />
              <TextField id="cp-pan" label="PAN" value={form.pan} onChange={(e) => set("pan", e.target.value)} />
            </div>
            <div className="form-grid">
              <SelectField
                id="cp-btype"
                label="Brokerage type"
                value={form.brokerage_type}
                onChange={(e) => set("brokerage_type", e.target.value as BrokerageType)}
                options={[
                  { value: "percent", label: "Percent of deal value" },
                  { value: "flat", label: "Flat amount per deal" },
                ]}
              />
              <TextField
                id="cp-brate"
                label={form.brokerage_type === "percent" ? "Rate (%)" : "Flat amount (₹)"}
                type="number"
                min={0}
                value={form.brokerage_rate}
                onChange={(e) => set("brokerage_rate", e.target.value)}
              />
            </div>
            <div className="form-grid">
              <TextField id="cp-bank" label="Payout bank a/c" value={form.payout_bank_account} onChange={(e) => set("payout_bank_account", e.target.value)} />
              <TextField id="cp-ifsc" label="IFSC" value={form.payout_ifsc} onChange={(e) => set("payout_ifsc", e.target.value)} />
            </div>
            <div className="form-grid">
              <TextField id="cp-upi" label="Payout UPI" value={form.payout_upi} onChange={(e) => set("payout_upi", e.target.value)} />
              <SelectField
                id="cp-active"
                label="Status"
                value={form.is_active ? "active" : "inactive"}
                onChange={(e) => set("is_active", e.target.value === "active")}
                options={[
                  { value: "active", label: "Active" },
                  { value: "inactive", label: "Inactive" },
                ]}
              />
            </div>
            <SelectField
              id="cp-user"
              label="Linked broker login (optional)"
              value={form.user_id}
              onChange={(e) => set("user_id", e.target.value)}
              options={[
                { value: "", label: "— Not linked —" },
                ...brokerUsers.map((u) => ({ value: u.id, label: `${u.first_name} ${u.last_name} · ${u.email}` })),
              ]}
              hint="Attach a broker user so this partner can sign into the portal."
            />
          </div>
        </Modal>
      )}

      {/* Detail */}
      {detail && (
        <Modal open title={detail.partner.company_name} size="lg" onClose={() => setDetail(null)}>
          <div className="stack" style={{ gap: "1rem" }}>
            <div className="kpi-grid">
              <div className="kpi"><div className="kpi__label">Referred</div><div className="kpi__value">{detail.partner.stats.leads_total}</div></div>
              <div className="kpi"><div className="kpi__label">Sold</div><div className="kpi__value">{detail.partner.stats.leads_sold}</div></div>
              <div className="kpi"><div className="kpi__label">Earned</div><div className="kpi__value">{formatInr(Number(detail.partner.stats.brokerage_accrued))}</div></div>
              <div className="kpi"><div className="kpi__label">Outstanding</div><div className="kpi__value">{formatInr(Number(detail.partner.stats.brokerage_outstanding))}</div></div>
            </div>

            {detailLoading ? (
              <p className="muted text-sm">Loading…</p>
            ) : (
              <>
                <div>
                  <div className="muted text-xs" style={{ textTransform: "uppercase", letterSpacing: ".04em", margin: "0.5rem 0" }}>Referred leads</div>
                  {detail.leads.length === 0 ? (
                    <p className="muted text-sm">No referrals yet.</p>
                  ) : (
                    <div className="stack" style={{ gap: "0.4rem" }}>
                      {detail.leads.map((l) => (
                        <div key={l.id} className="row row--between" style={{ padding: "0.4rem 0.6rem", border: "1px solid var(--color-border)", borderRadius: "var(--radius-sm)" }}>
                          <span className="text-sm"><strong>{l.contact_name}</strong> <span className="muted">· #{l.lead_number}</span></span>
                          <Badge tone="neutral">{l.stage_code}</Badge>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {canPayout && (
                  <div>
                    <div className="muted text-xs" style={{ textTransform: "uppercase", letterSpacing: ".04em", margin: "0.5rem 0" }}>Brokerage payouts</div>
                    {detail.payouts.length === 0 ? (
                      <p className="muted text-sm">No brokerage accrued yet.</p>
                    ) : (
                      <div className="stack" style={{ gap: "0.4rem" }}>
                        {detail.payouts.map((p) => (
                          <div key={p.id} className="row row--between" style={{ alignItems: "center", padding: "0.4rem 0.6rem", border: "1px solid var(--color-border)", borderRadius: "var(--radius-sm)" }}>
                            <span className="text-sm">
                              {formatDate(p.created_at)} · <strong>{formatInr(Number(p.amount))}</strong>{" "}
                              <span className="muted">· {p.status}{p.paid_on ? ` on ${formatDate(p.paid_on)}` : ""}</span>
                            </span>
                            {p.status === "accrued" && (
                              <Button size="sm" variant="secondary" onClick={() => void markPaid(p)}>Mark paid</Button>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
