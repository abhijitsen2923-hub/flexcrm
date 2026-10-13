import { Check } from "lucide-react";

interface StepperProps {
  steps: readonly string[];
  current: number; // 0-based
  // Which steps show a tick (default: every step before the current one).
  isDone?: (index: number) => boolean;
  // Makes the steps clickable. The page decides what a click on a later step does (e.g. check the steps between).
  onSelect?: (index: number) => void;
  label?: string;
}

/**
 * Numbered step indicator for multi-step forms: circles joined by a line, a tick on finished steps. On phones only
 * the circles show, with the current step's name underneath (seven labels don't fit a phone's width).
 */
export function Stepper({ steps, current, isDone, onSelect, label = "Progress" }: StepperProps) {
  return (
    <nav className="stepper" aria-label={label}>
      <ol className="stepper__list">
        {steps.map((name, index) => {
          const active = index === current;
          const done = !active && (isDone ? isDone(index) : index < current);
          const body = (
            <>
              <span className="stepper__circle" aria-hidden="true">
                {done ? <Check size={14} strokeWidth={3} /> : index + 1}
              </span>
              <span className="stepper__label">{name}</span>
            </>
          );
          return (
            <li
              key={name}
              className={["stepper__item", active ? "is-active" : done ? "is-done" : null].filter(Boolean).join(" ")}
              aria-current={active ? "step" : undefined}
            >
              {onSelect ? (
                <button
                  type="button"
                  className="stepper__btn"
                  disabled={active}
                  onClick={() => onSelect(index)}
                  aria-label={`Step ${index + 1}: ${name}${done ? " (done)" : ""}`}
                >
                  {body}
                </button>
              ) : (
                <div className="stepper__btn">{body}</div>
              )}
            </li>
          );
        })}
      </ol>
      <p className="stepper__current" aria-hidden="true">
        Step {current + 1} of {steps.length} · <strong>{steps[current]}</strong>
      </p>
    </nav>
  );
}
