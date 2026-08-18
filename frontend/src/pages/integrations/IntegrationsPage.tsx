import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Badge, Button, LoadingBlock, Modal, TextField, useToast } from "../../components";
import { useOrgModules } from "../../context/OrgContext";
import {
  integrationsService,
  type MetaConnection,
  type MetaOAuthPage,
  type MetaValidateResult,
} from "../../services/integrations";
import { extractErrorMessage } from "../../utils/errors";
import { formatDateTime } from "../../utils/format";

const STATUS_TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  ok: "success",
  needs_reauth: "warning",
  error: "danger",
};
const STATUS_LABEL: Record<string, string> = {
  ok: "Connected",
  needs_reauth: "Reconnect needed",
  error: "Error",
};
const REASON_HELP: Record<string, string> = {
  invalid_token:
    "The token is invalid or expired — generate a fresh never-expiring System-User token and paste it again.",
  missing_lead_access:
    "Grant this System User Lead Access on the Page (Business Settings → Integrations → Leads Access) and accept the Lead Ads Terms of Service, then retry.",
  error: "Meta rejected the request — see the detail below.",
};

const SETUP_STEPS = [
  "Use a Business Manager that OWNS the Facebook Page (and linked Instagram).",
  "Complete Meta Business Verification (unverified portfolios get blocked/throttled).",
  "Create a Business-type Meta App inside that Business.",
  "Business Settings → Users → System Users: create a System User; assign the Page (manage-leads) + the app.",
  "Generate a System-User access token (expiration = Never) with scopes: leads_retrieval, pages_show_list, pages_read_engagement, pages_manage_ads, business_management.",
  "Business Settings → Integrations → Leads Access: grant that System User Lead Access and accept the Lead Ads Terms of Service.",
  "Paste the token + your Page ID below and click Test connection, then Connect.",
];

export default function IntegrationsPage() {
  const toast = useToast();
  const orgModules = useOrgModules();
  // FB & IG share one connection; the poll ingests only platforms enabled for
  // this workspace (per-tenant admin toggles). Show which are active.
  const activePlatforms = [
    orgModules.meta_facebook ? "Facebook" : null,
    orgModules.meta_instagram ? "Instagram" : null,
  ].filter(Boolean) as string[];
  const [connections, setConnections] = useState<MetaConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [pageId, setPageId] = useState("");
  const [token, setToken] = useState("");
  const [probe, setProbe] = useState<MetaValidateResult | null>(null);
  const [busy, setBusy] = useState<"test" | "connect" | null>(null);

  // OAuth "Connect Facebook" flow.
  const [oauthBusy, setOauthBusy] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerHandle, setPickerHandle] = useState<string | null>(null);
  const [pickerPages, setPickerPages] = useState<MetaOAuthPage[]>([]);
  const [pickerLoading, setPickerLoading] = useState(false);
  const [pickerBusy, setPickerBusy] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [searchParams, setSearchParams] = useSearchParams();
  const oauthHandledRef = useRef(false);

  async function refresh() {
    setLoading(true);
    try {
      setConnections(await integrationsService.listMeta());
    } catch {
      /* leave the list as-is; the connect form still works */
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refresh();
  }, []);

  // Handle the return leg of the OAuth round-trip: Meta's callback redirects the browser to
  // /integrations?meta_oauth=<handle> (or ?meta_oauth_error=...). Consume it exactly once,
  // strip the params (so a refresh/back can't replay a spent handle), then open the picker.
  async function openPicker(handle: string) {
    setPickerHandle(handle);
    setPickerOpen(true);
    setPickerLoading(true);
    setPickerPages([]);
    setSelectedIds([]);
    try {
      const pages = await integrationsService.getMetaOAuthSession(handle);
      setPickerPages(pages);
      // Pre-select when there's a single obvious choice; otherwise let the admin pick.
      setSelectedIds(pages.length === 1 ? pages.map((p) => p.id) : []);
    } catch (err) {
      setPickerOpen(false);
      setPickerHandle(null);
      toast.error("Connect session expired", extractErrorMessage(err));
    } finally {
      setPickerLoading(false);
    }
  }

  useEffect(() => {
    if (oauthHandledRef.current) return;
    const handle = searchParams.get("meta_oauth");
    const oauthError = searchParams.get("meta_oauth_error");
    if (!handle && !oauthError) return;
    oauthHandledRef.current = true;
    const next = new URLSearchParams(searchParams);
    next.delete("meta_oauth");
    next.delete("meta_oauth_error");
    setSearchParams(next, { replace: true });
    if (oauthError) {
      toast.error("Facebook connect not completed", "The connection was cancelled or failed — you can try again.");
      return;
    }
    if (handle) void openPicker(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  async function startOAuth() {
    setOauthBusy(true);
    try {
      const { authorize_url } = await integrationsService.startMetaOAuth();
      // Leave the SPA for Facebook's consent screen; Meta returns to /integrations after.
      window.location.href = authorize_url;
    } catch (err) {
      toast.error("Couldn't start Facebook connect", extractErrorMessage(err));
      setOauthBusy(false); // on success we're navigating away, so only reset on failure
    }
  }

  function togglePage(id: string) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  function closePicker() {
    if (pickerBusy) return;
    setPickerOpen(false);
    setPickerHandle(null);
  }

  async function connectSelected() {
    if (!pickerHandle || selectedIds.length === 0) return;
    setPickerBusy(true);
    try {
      const created = await integrationsService.connectMetaOAuth(pickerHandle, selectedIds);
      toast.success(
        "Connected",
        `${created.length} page${created.length === 1 ? "" : "s"} connected — leads will start syncing shortly.`
      );
      await refresh();
    } catch (err) {
      toast.error("Could not connect", extractErrorMessage(err));
    } finally {
      // The handle is one-time (consumed server-side on the first attempt), so always close.
      setPickerBusy(false);
      setPickerOpen(false);
      setPickerHandle(null);
    }
  }

  async function testConnection() {
    if (!pageId.trim() || !token.trim()) return;
    setBusy("test");
    setProbe(null);
    try {
      setProbe(await integrationsService.validateMeta(pageId.trim(), token.trim()));
    } catch (err) {
      toast.error("Test failed", extractErrorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function connect() {
    if (!pageId.trim() || !token.trim()) return;
    setBusy("connect");
    try {
      await integrationsService.connectMeta({ page_id: pageId.trim(), token: token.trim() });
      toast.success("Connected", "Facebook / Instagram leads will start syncing shortly.");
      setPageId("");
      setToken("");
      setProbe(null);
      await refresh();
    } catch (err) {
      toast.error("Could not connect", extractErrorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function disconnect(conn: MetaConnection) {
    try {
      await integrationsService.disconnectMeta(conn.id);
      toast.success("Disconnected", conn.page_name ?? conn.page_id);
      await refresh();
    } catch (err) {
      toast.error("Disconnect failed", extractErrorMessage(err));
    }
  }

  return (
    <div className="stack" style={{ gap: "1.25rem" }}>
      <div>
        <h1>Integrations</h1>
        <p className="muted">
          Connect <strong>Facebook &amp; Instagram Lead Ads</strong> — new lead-form submissions flow
          into your pipeline as fresh enquiries, tagged by source.
        </p>
        {activePlatforms.length > 0 ? (
          <p className="text-xs muted" style={{ marginTop: "0.35rem" }}>
            Enabled for your workspace: <strong>{activePlatforms.join(" & ")}</strong>. One connection
            covers both platforms; leads from a platform that isn&apos;t enabled are skipped.
          </p>
        ) : null}
      </div>

      {/* Existing connections */}
      <div className="card" style={{ padding: "1rem 1.25rem" }}>
        <div className="row row--between" style={{ alignItems: "center", marginBottom: "0.5rem" }}>
          <strong>Connected pages</strong>
          <Button size="sm" variant="ghost" onClick={() => void refresh()}>Refresh</Button>
        </div>
        {loading ? (
          <LoadingBlock />
        ) : connections.length === 0 ? (
          <p className="muted text-sm">No connections yet — add one below.</p>
        ) : (
          <div className="stack" style={{ gap: "0.5rem" }}>
            {connections.map((conn) => (
              <div key={conn.id} className="row row--between" style={{ alignItems: "center", padding: "0.5rem 0", borderTop: "1px solid var(--color-border)" }}>
                <div className="stack" style={{ gap: "0.15rem" }}>
                  <span>
                    <strong>{conn.page_name ?? conn.page_id}</strong>{" "}
                    <span className="muted text-xs">· Page {conn.page_id}</span>
                  </span>
                  <span className="text-xs muted">
                    {conn.auth_type === "oauth" ? "via Facebook login" : "via token"}
                    {" · "}
                    {conn.last_synced_at ? `Last synced ${formatDateTime(conn.last_synced_at)}` : "Not synced yet"}
                    {conn.status_detail ? ` · ${conn.status_detail}` : ""}
                  </span>
                </div>
                <div className="row" style={{ gap: "0.5rem", alignItems: "center" }}>
                  <Badge tone={STATUS_TONE[conn.status] ?? "neutral"}>
                    {STATUS_LABEL[conn.status] ?? conn.status}
                  </Badge>
                  <Button size="sm" variant="ghost" onClick={() => void disconnect(conn)}>Disconnect</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Primary: one-click Connect Facebook */}
      <div className="card" style={{ padding: "1rem 1.25rem" }}>
        <strong>Add a connection</strong>
        <p className="muted text-sm" style={{ marginTop: "0.35rem" }}>
          Sign in with Facebook and choose which Page(s) to sync — the simplest way to connect.
          Leads then arrive in real time, and we keep the connection refreshed for you.
        </p>
        <div className="row" style={{ marginTop: "0.75rem" }}>
          <Button
            loading={oauthBusy}
            disabled={oauthBusy}
            onClick={() => void startOAuth()}
          >
            Connect Facebook
          </Button>
        </div>
      </div>

      {/* Advanced: bring-your-own System-User token (the original method) */}
      <details className="card" style={{ padding: "0.75rem 1.25rem" }}>
        <summary style={{ cursor: "pointer", fontWeight: 600 }}>
          Advanced: connect with a System-User token
        </summary>
        <p className="muted text-xs" style={{ margin: "0.6rem 0 0.25rem" }}>
          Prefer to bring your own never-expiring token (no Facebook login redirect)? Follow these
          one-time steps, paste your token, and connect. Note: real-time webhooks aren&apos;t available
          on this method — leads are polled every few minutes.
        </p>
        <ol className="stack" style={{ gap: "0.35rem", margin: "0.5rem 0 0.75rem", paddingLeft: "1.1rem" }}>
          {SETUP_STEPS.map((s, i) => (
            <li key={i} className="text-sm">{s}</li>
          ))}
        </ol>

        <div className="form-grid" style={{ marginTop: "0.5rem" }}>
          <TextField
            id="meta-page-id"
            label="Facebook Page ID"
            value={pageId}
            onChange={(e) => setPageId(e.target.value)}
            placeholder="e.g. 1029384756"
          />
          <TextField
            id="meta-token"
            label="System-User access token"
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Paste the never-expiring token"
            hint="Stored encrypted; never shown again."
          />
        </div>
        {probe && (
          <div
            className={`text-sm ${probe.ok ? "" : "error-banner"}`}
            style={{ marginTop: "0.6rem", ...(probe.ok ? { color: "var(--color-success, #16a34a)" } : {}) }}
          >
            {probe.ok ? (
              <>✓ Token valid — <strong>{probe.page_name}</strong> ({probe.form_count ?? 0} lead form{probe.form_count === 1 ? "" : "s"}).</>
            ) : (
              <>
                {REASON_HELP[probe.reason ?? "error"] ?? "Validation failed."}
                {probe.detail ? <div className="muted text-xs" style={{ marginTop: 4 }}>{probe.detail}</div> : null}
              </>
            )}
          </div>
        )}
        <div className="row" style={{ gap: "0.5rem", marginTop: "0.75rem", justifyContent: "flex-end" }}>
          <Button
            variant="secondary"
            loading={busy === "test"}
            disabled={!pageId.trim() || !token.trim() || busy !== null}
            onClick={() => void testConnection()}
          >
            Test connection
          </Button>
          <Button
            loading={busy === "connect"}
            disabled={!pageId.trim() || !token.trim() || busy !== null}
            onClick={() => void connect()}
          >
            Connect
          </Button>
        </div>
      </details>

      {/* OAuth Page picker */}
      <Modal
        open={pickerOpen}
        title="Choose which Page(s) to connect"
        onClose={closePicker}
        footer={
          <>
            <Button variant="ghost" disabled={pickerBusy} onClick={closePicker}>Cancel</Button>
            <Button
              loading={pickerBusy}
              disabled={pickerBusy || selectedIds.length === 0}
              onClick={() => void connectSelected()}
            >
              Connect{selectedIds.length > 0 ? ` (${selectedIds.length})` : ""}
            </Button>
          </>
        }
      >
        {pickerLoading ? (
          <LoadingBlock />
        ) : pickerPages.length === 0 ? (
          <p className="muted text-sm">
            No Facebook Pages were found for this account. Make sure your login manages at least one
            Page, then try again.
          </p>
        ) : (
          <div className="stack" style={{ gap: "0.3rem" }}>
            {pickerPages.map((p) => (
              <label
                key={p.id}
                className="row"
                style={{ alignItems: "center", gap: "0.65rem", padding: "0.4rem 0", cursor: "pointer" }}
              >
                <input
                  type="checkbox"
                  checked={selectedIds.includes(p.id)}
                  onChange={() => togglePage(p.id)}
                />
                <span className="stack" style={{ gap: "0.1rem" }}>
                  <strong>{p.name ?? p.id}</strong>
                  <span className="text-xs muted">
                    Page {p.id}{p.has_instagram ? " · Instagram linked" : ""}
                  </span>
                </span>
              </label>
            ))}
          </div>
        )}
      </Modal>
    </div>
  );
}
