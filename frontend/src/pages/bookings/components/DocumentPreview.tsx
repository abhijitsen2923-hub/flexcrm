import { useState } from "react";
import { Download, Printer, X } from "lucide-react";
import { Button } from "../../../components";
import "./DocumentPreview.css";

interface Props {
  url: string;
  title?: string;
  onClose: () => void;
}

export function DocumentPreview({ url, title = "Document", onClose }: Props) {
  const [loadError, setLoadError] = useState(false);

  return (
    <div className="doc-preview" role="dialog" aria-label={title}>
      <div className="doc-preview__header">
        <span className="doc-preview__title">{title}</span>
        <div className="doc-preview__actions">
          <Button
            variant="ghost"
            size="sm"
            icon={<Download size={14} />}
            onClick={() => window.open(url, "_blank", "noopener")}
          >
            Download
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon={<Printer size={14} />}
            onClick={() => {
              const win = window.open(url, "_blank", "noopener");
              win?.addEventListener("load", () => win.print());
            }}
          >
            Print
          </Button>
          <button className="doc-preview__close" onClick={onClose} aria-label="Close preview">
            <X size={16} />
          </button>
        </div>
      </div>

      {loadError ? (
        <div className="doc-preview__error">
          <p>Unable to load document.</p>
          <Button variant="secondary" size="sm" onClick={() => window.open(url, "_blank", "noopener")}>
            Open in new tab
          </Button>
        </div>
      ) : (
        <iframe
          src={url}
          title={title}
          className="doc-preview__frame"
          onError={() => setLoadError(true)}
        />
      )}
    </div>
  );
}
