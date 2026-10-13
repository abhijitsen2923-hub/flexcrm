// Small building blocks shared by the project wizard's steps (cards, inline errors, the error summary).
import type { InputHTMLAttributes, ReactNode } from "react";
import { AlertTriangle, Info } from "lucide-react";
import type { Project } from "../../../types/realestate";
import { isStepOk, type StepCheck, type WizardState } from "../../../utils/projectWizard";

export interface StepProps {
  state: WizardState;
  update: (change: (state: WizardState) => WizardState) => void;
  // The step's problems — null until the user has tried to move on from it (no red before they've had a go).
  check: StepCheck | null;
  project: Project | null; // the project being edited (null = Add project)
}

/** The message for one field, when the step's problems are showing. */
export function fieldError(check: StepCheck | null, key: string): string | undefined {
  return check?.fields[key];
}

export function Req({ children }: { children: ReactNode }) {
  return (
    <>
      {children}
      <span className="pw-req" aria-hidden="true">
        {" "}
        *
      </span>
    </>
  );
}

export function StepIntro({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="pw-step__intro">
      <h3>{title}</h3>
      {children && <p>{children}</p>}
    </div>
  );
}

export function WizardCard({
  title,
  icon,
  subtitle,
  actions,
  children,
}: {
  title: ReactNode;
  icon?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="pw-card">
      <header className="pw-card__head">
        <div className="pw-card__heading">
          <div className="pw-card__title">
            {icon}
            <span>{title}</span>
          </div>
          {subtitle && <div className="pw-card__subtitle">{subtitle}</div>}
        </div>
        {actions && <div className="pw-card__actions">{actions}</div>}
      </header>
      <div className="pw-card__body">{children}</div>
    </section>
  );
}

/** "Fix the 3 highlighted fields" + any problem that isn't tied to one field. */
export function StepErrors({ check }: { check: StepCheck | null }) {
  if (!check || isStepOk(check)) return null;
  const count = Object.keys(check.fields).length;
  return (
    <div className="error-banner pw-errors" role="alert">
      {count > 0 && (
        <div>
          Fix the {count === 1 ? "highlighted field" : `${count} highlighted fields`} to continue.
        </div>
      )}
      {check.general.map((message) => (
        <div key={message}>{message}</div>
      ))}
    </div>
  );
}

export function Note({ tone = "info", children }: { tone?: "info" | "warn"; children: ReactNode }) {
  return (
    <div className={`pw-note pw-note--${tone}`}>
      {tone === "warn" ? <AlertTriangle size={15} aria-hidden="true" /> : <Info size={15} aria-hidden="true" />}
      <div>{children}</div>
    </div>
  );
}

/** A compact input for table cells, with its message underneath. */
export function CellInput({
  error,
  className,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { error?: string }) {
  return (
    <div className="pw-cell">
      <input
        className={["input", error ? "is-invalid" : null, className].filter(Boolean).join(" ")}
        aria-invalid={error ? true : undefined}
        {...rest}
      />
      {error && <div className="pw-cell__error">{error}</div>}
    </div>
  );
}

/** Indian-style whole rupees: ₹62,50,000. */
export function rupees(amount: number | null | undefined): string {
  if (amount == null || !Number.isFinite(amount)) return "—";
  return `₹${Math.round(amount).toLocaleString("en-IN")}`;
}

export function sqft(area: number | null | undefined): string {
  if (area == null || !Number.isFinite(area)) return "—";
  return `${area.toLocaleString("en-IN")} sq ft`;
}
