import { X } from "lucide-react";
import { useEffect, type PropsWithChildren, type ReactNode } from "react";
import { createPortal } from "react-dom";


interface ModalProps extends PropsWithChildren {
  open: boolean;
  title?: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
  size?: "md" | "lg";
}


export function Modal({ open, title, footer, onClose, size = "md", children }: ModalProps) {
  useEffect(() => {
    if (!open) {
      return;
    }
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handler);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", handler);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  return createPortal(
    <div className="modal-backdrop" role="dialog" aria-modal="true" onClick={onClose}>
      <div
        className={["modal", size === "lg" ? "modal--lg" : null].filter(Boolean).join(" ")}
        onClick={(event) => event.stopPropagation()}
      >
        {title !== undefined && (
          <header className="modal__header">
            <h2 style={{ fontSize: "1.05rem" }}>{title}</h2>
            <button type="button" className="btn btn--ghost btn--icon" onClick={onClose} aria-label="Close">
              <X size={18} />
            </button>
          </header>
        )}
        <div className="modal__body">{children}</div>
        {footer && <footer className="modal__footer">{footer}</footer>}
      </div>
    </div>,
    document.body
  );
}
