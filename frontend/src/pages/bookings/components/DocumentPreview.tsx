import { useState, useRef } from "react";
import { Download, FileDown, Printer, X } from "lucide-react";
import { Button } from "../../../components";
import { bookingsService } from "../../../services/bookings";
import "./DocumentPreview.css";

type DocType = "booking_form" | "allotment_letter" | "receipt";

interface Props {
  html: string;
  title?: string;
  onClose: () => void;
  // When provided, shows a "Download PDF" action that renders a real PDF
  // server-side (stored to object storage) and opens the presigned URL.
  pdf?: { bookingId: string; docType: DocType };
}

export function DocumentPreview({ html, title = "Document", onClose, pdf }: Props) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  function download() {
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title.replace(/\s+/g, "-").toLowerCase()}.html`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function downloadPdf() {
    if (!pdf) return;
    setDownloadingPdf(true);
    setPdfError(null);
    try {
      const { url } = await bookingsService.getDocumentPdfUrl(pdf.bookingId, pdf.docType);
      window.open(url, "_blank", "noopener");
    } catch {
      // 503 → storage not configured yet; anything else → generation failed.
      setPdfError("PDF unavailable — file storage isn't configured yet.");
    } finally {
      setDownloadingPdf(false);
    }
  }

  function print() {
    const win = frameRef.current?.contentWindow;
    if (win) {
      win.focus();
      win.print();
    }
  }

  return (
    <div className="doc-preview" role="dialog" aria-label={title}>
      <div className="doc-preview__header">
        <span className="doc-preview__title">{title}</span>
        <div className="doc-preview__actions">
          {pdf && (
            <Button
              variant="ghost"
              size="sm"
              icon={<FileDown size={14} />}
              onClick={downloadPdf}
              loading={downloadingPdf}
            >
              Download PDF
            </Button>
          )}
          <Button variant="ghost" size="sm" icon={<Download size={14} />} onClick={download}>
            Download HTML
          </Button>
          <Button variant="ghost" size="sm" icon={<Printer size={14} />} onClick={print}>
            Print
          </Button>
          <button className="doc-preview__close" onClick={onClose} aria-label="Close preview">
            <X size={16} />
          </button>
        </div>
      </div>

      {pdfError && <div className="doc-preview__error">{pdfError}</div>}

      <iframe
        ref={frameRef}
        srcDoc={html}
        title={title}
        className="doc-preview__frame"
      />
    </div>
  );
}
