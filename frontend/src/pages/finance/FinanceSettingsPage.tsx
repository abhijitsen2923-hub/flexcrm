import { useEffect, useState } from "react";

import { Button, Card, LoadingBlock, TextField, useToast } from "../../components";
import { usePermissions } from "../../hooks/usePermissions";
import { financeService } from "../../services/finance";
import type { FinanceSettings } from "../../types/finance";
import { extractErrorMessage } from "../../utils/errors";

const MODE_LABELS: Record<string, string> = {
  general: "General Business",
  re_builder: "Real Estate — Builder / Developer",
  re_broker: "Real Estate — Broker / Consultant",
  hybrid: "Hybrid Business"
};

export default function FinanceSettingsPage() {
  const toast = useToast();
  const { has } = usePermissions();
  const canManage = has("FINANCE_SETTINGS_MANAGE");

  const [settings, setSettings] = useState<FinanceSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ gst_registered: false, gstin: "", home_state_code: "" });

  useEffect(() => {
    void (async () => {
      try {
        const s = await financeService.getSettings();
        setSettings(s);
        setForm({ gst_registered: s.gst_registered, gstin: s.gstin ?? "", home_state_code: s.home_state_code ?? "" });
      } catch (e) {
        toast.error("Failed to load settings", extractErrorMessage(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function save() {
    setSaving(true);
    try {
      const s = await financeService.updateSettings({
        gst_registered: form.gst_registered,
        gstin: form.gstin || null,
        home_state_code: form.home_state_code || null
      });
      setSettings(s);
      toast.success("Settings saved");
    } catch (e) {
      toast.error("Save failed", extractErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <LoadingBlock label="Loading settings…" />;

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Finance Settings</h1>
          <p>GST configuration and business mode.</p>
        </div>
      </div>

      <Card title="Business mode">
        <p className="muted text-sm">
          This organisation is set to{" "}
          <strong>{MODE_LABELS[settings?.finance_business_mode ?? "general"]}</strong>. It decides which
          income and expense categories appear. Ask your platform admin to change it.
        </p>
      </Card>

      <Card title="GST">
        <div className="form" style={{ maxWidth: 480 }}>
          <label className="row" style={{ gap: "0.5rem", alignItems: "center" }}>
            <input
              type="checkbox"
              disabled={!canManage}
              checked={form.gst_registered}
              onChange={(e) => setForm({ ...form, gst_registered: e.target.checked })}
            />
            <span>GST registered</span>
          </label>
          <TextField
            id="s-gstin"
            label="GSTIN"
            value={form.gstin}
            disabled={!canManage}
            onChange={(e) => setForm({ ...form, gstin: e.target.value })}
          />
          <TextField
            id="s-state"
            label="Home state code (e.g. 27)"
            value={form.home_state_code}
            disabled={!canManage}
            onChange={(e) => setForm({ ...form, home_state_code: e.target.value })}
            hint="Used to default intra-state vs inter-state GST on bills and expenses."
          />
          {canManage && (
            <div>
              <Button loading={saving} onClick={() => void save()}>Save settings</Button>
            </div>
          )}
        </div>
      </Card>
    </>
  );
}
