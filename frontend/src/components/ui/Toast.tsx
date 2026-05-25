import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren
} from "react";
import { createPortal } from "react-dom";


type ToastTone = "success" | "error" | "info" | "warning";

interface ToastInput {
  title: string;
  body?: string;
  tone?: ToastTone;
  durationMs?: number;
}

interface ToastEntry extends Required<Pick<ToastInput, "title">> {
  id: number;
  body?: string;
  tone: ToastTone;
}

interface ToastContextValue {
  push: (input: ToastInput) => void;
  success: (title: string, body?: string) => void;
  error: (title: string, body?: string) => void;
  info: (title: string, body?: string) => void;
  warning: (title: string, body?: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);


export function ToastProvider({ children }: PropsWithChildren) {
  const [items, setItems] = useState<ToastEntry[]>([]);
  const counter = useRef(0);

  const dismiss = useCallback((id: number) => {
    setItems((current) => current.filter((entry) => entry.id !== id));
  }, []);

  const push = useCallback(
    (input: ToastInput) => {
      counter.current += 1;
      const id = counter.current;
      const entry: ToastEntry = {
        id,
        title: input.title,
        body: input.body,
        tone: input.tone ?? "info"
      };
      setItems((current) => [...current, entry]);
      const duration = input.durationMs ?? 4500;
      window.setTimeout(() => dismiss(id), duration);
    },
    [dismiss]
  );

  const value = useMemo<ToastContextValue>(
    () => ({
      push,
      success: (title, body) => push({ title, body, tone: "success" }),
      error: (title, body) => push({ title, body, tone: "error", durationMs: 6000 }),
      info: (title, body) => push({ title, body, tone: "info" }),
      warning: (title, body) => push({ title, body, tone: "warning" })
    }),
    [push]
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      {typeof document !== "undefined" &&
        createPortal(
          <div className="toast-stack" role="status" aria-live="polite">
            {items.map((entry) => (
              <div key={entry.id} className={`toast toast--${entry.tone}`}>
                <div className="grow">
                  <div className="toast__title">{entry.title}</div>
                  {entry.body && <div className="toast__body">{entry.body}</div>}
                </div>
              </div>
            ))}
          </div>,
          document.body
        )}
    </ToastContext.Provider>
  );
}


export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return context;
}
