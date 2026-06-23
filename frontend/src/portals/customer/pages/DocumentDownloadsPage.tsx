import { Download } from "lucide-react";
import { useEffect, useState } from "react";
import {
  customerPortalService,
  type CustomerDocument
} from "../../../services/customerPortal";

const DOC_LABELS: Record<CustomerDocument["type"], string> = {
  booking_form:       "Booking Form",
  allotment_letter:   "Allotment Letter",
  demand_note:        "Demand Note",
  receipt:            "Payment Receipt",
  possession_letter:  "Possession Letter",
};

const DOC_ICON: Record<CustomerDocument["type"], string> = {
  booking_form:       "📋",
  allotment_letter:   "📜",
  demand_note:        "💰",
  receipt:            "🧾",
  possession_letter:  "🏠",
};

type LoadState = "loading" | "ok" | "error";

function DocCard({ doc }: { doc: CustomerDocument }) {
  const [downloading, setDownloading] = useState(false);

  async function handleDownload() {
    setDownloading(true);
    try {
      const url = await customerPortalService.getDocumentUrl(doc.id);
      const a = Object.assign(document.createElement("a"), {
        href: url,
        download: `${DOC_LABELS[doc.type]}.pdf`,
        target: "_blank",
        rel: "noopener noreferrer"
      });
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch {
      alert("Download failed. Please try again.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div
      className="cp-card"
      style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}
    >
      <div style={{ fontSize: "2rem", lineHeight: 1 }}>
        {DOC_ICON[doc.type]}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 600 }}>{doc.name || DOC_LABELS[doc.type]}</div>
        <div style={{ fontSize: "var(--cp-font-xs)", color: "var(--cp-text-muted)", marginTop: 2 }}>
          {DOC_LABELS[doc.type]} ·{" "}
          {new Date(doc.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}
        </div>
      </div>
      <button
        className="cp-btn"
        style={{ width: "auto", padding: "var(--space-2) var(--space-3)", minHeight: "var(--tap-target-min)" }}
        onClick={() => void handleDownload()}
        disabled={downloading}
        aria-label={`Download ${DOC_LABELS[doc.type]}`}
      >
        <Download size={16} />
        {downloading ? "…" : "Save"}
      </button>
    </div>
  );
}

export default function DocumentDownloadsPage() {
  const [docs, setDocs] = useState<CustomerDocument[]>([]);
  const [state, setState] = useState<LoadState>("loading");

  useEffect(() => {
    void customerPortalService
      .getDocuments()
      .then((rows) => { setDocs(rows); setState("ok"); })
      .catch(() => setState("error"));
  }, []);

  if (state === "loading") {
    return (
      <div className="cp-empty">
        <div className="cp-empty__icon">⏳</div>
        <div className="cp-empty__title">Loading documents…</div>
      </div>
    );
  }

  if (state === "error") {
    return (
      <div className="cp-empty">
        <div className="cp-empty__icon">⚠️</div>
        <div className="cp-empty__title">Could not load documents</div>
        <div className="cp-empty__desc">Check your connection and try again.</div>
      </div>
    );
  }

  return (
    <>
      <h1 className="cp-page-title">Documents</h1>
      {docs.length === 0 ? (
        <div className="cp-empty">
          <div className="cp-empty__icon">📂</div>
          <div className="cp-empty__title">No documents yet</div>
          <div className="cp-empty__desc">
            Your booking form, allotment letter, and receipts will appear here once generated.
          </div>
        </div>
      ) : (
        docs.map((doc) => <DocCard key={doc.id} doc={doc} />)
      )}
    </>
  );
}
