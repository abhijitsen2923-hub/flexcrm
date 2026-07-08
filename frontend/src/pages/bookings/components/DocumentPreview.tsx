import { useRef } from "react";
import { Download, Printer, X } from "lucide-react";
import { Button } from "../../../components";
import "./DocumentPreview.css";

interface Props {
  html: string;
  title?: string;
  onClose: () => void;
}

export function DocumentPreview({ html, title = "Document", onClose }: Props) {
  const frameRef = useRef<HTMLIFrameElement>(null);

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
          <Button variant="ghost" size="sm" icon={<Download size={14} />} onClick={download}>
            Download
          </Button>
          <Button variant="ghost" size="sm" icon={<Printer size={14} />} onClick={print}>
            Print / Save PDF
          </Button>
          <button className="doc-preview__close" onClick={onClose} aria-label="Close preview">
            <X size={16} />
          </button>
        </div>
      </div>

      <iframe
        ref={frameRef}
        srcDoc={html}
        title={title}
        className="doc-preview__frame"
      />
    </div>
  );
}
