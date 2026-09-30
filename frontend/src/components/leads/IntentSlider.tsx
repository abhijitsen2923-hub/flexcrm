import { useRef, type KeyboardEvent, type PointerEvent } from "react";

import type { LeadIntent } from "../../types";
import { INTENT_OPTIONS, intentAtRatio, intentIndex, stepIntent } from "../../utils/leadIntent";
import { IntentBadge } from "./IntentBadge";

interface IntentSliderProps {
  // DOM id of the slider itself (the stage-change dialog scrolls to it when intent is missing).
  id: string;
  value: LeadIntent | null;
  onChange: (intent: LeadIntent) => void;
  required?: boolean;
  hint?: string;
  error?: string;
  disabled?: boolean;
  // Intent is fixed here (Booked onward / closed stages): show it read-only instead of the slider.
  locked?: boolean;
  lockedNote?: string;
}

// How far a finger/mouse must travel before it's a drag (below it, releasing is a tap).
const DRAG_THRESHOLD_PX = 6;

/**
 * Compact Low · Medium · High bar. Nothing is pre-selected: until the user taps or drags, there is no handle
 * and it reads "Not set". A tap or a sideways drag picks a value; a vertical swipe that starts on the bar
 * scrolls the page instead (so a stray touch never "chooses" for the user). Keyboard: arrows move one step
 * (from "not set" they land on Medium), Home / End jump to the ends.
 */
export function IntentSlider({
  id,
  value,
  onChange,
  required = false,
  hint,
  error,
  disabled = false,
  locked = false,
  lockedNote = "fixed from Booked onward",
}: IntentSliderProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  // The gesture in progress: where it started, and whether it has become a sideways drag.
  const gesture = useRef<{ x: number; y: number; dragging: boolean; pointerId: number } | null>(null);
  const labelId = `${id}-label`;

  if (locked) {
    return (
      <div className="intent intent--locked">
        <div className="intent__locked-row">
          <span className="intent__label">Intent</span>
          <IntentBadge intent={value} />
        </div>
        <span className="intent__hint">{lockedNote}</span>
      </div>
    );
  }

  const index = intentIndex(value);
  const current = index >= 0 ? INTENT_OPTIONS[index] : null;

  function pick(clientX: number) {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return;
    const next = intentAtRatio((clientX - rect.left) / rect.width);
    if (next !== value) onChange(next);
  }

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    // Main button / first finger only — a right or middle click never picks a value.
    if (disabled || !event.isPrimary || event.button !== 0) return;
    gesture.current = { x: event.clientX, y: event.clientY, dragging: false, pointerId: event.pointerId };
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    const g = gesture.current;
    if (!g || g.pointerId !== event.pointerId) return;
    const dx = Math.abs(event.clientX - g.x);
    const dy = Math.abs(event.clientY - g.y);
    if (!g.dragging) {
      if (dx < DRAG_THRESHOLD_PX && dy < DRAG_THRESHOLD_PX) return;
      if (dy > dx) {
        gesture.current = null; // a vertical swipe: let the page scroll, pick nothing
        return;
      }
      g.dragging = true;
      event.currentTarget.setPointerCapture?.(event.pointerId);
    }
    pick(event.clientX);
  }

  function onPointerUp(event: PointerEvent<HTMLDivElement>) {
    const g = gesture.current;
    gesture.current = null;
    if (!g || g.pointerId !== event.pointerId) return;
    // A tap (no drag) picks where it landed; a drag already picked as it moved.
    if (!g.dragging) pick(event.clientX);
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (disabled) return;
    let next: LeadIntent | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowUp") next = stepIntent(value, 1);
    else if (event.key === "ArrowLeft" || event.key === "ArrowDown") next = stepIntent(value, -1);
    else if (event.key === "Home") next = "low";
    else if (event.key === "End") next = "high";
    if (!next) return;
    event.preventDefault();
    if (next !== value) onChange(next);
  }

  return (
    <div className="intent">
      <div className="intent__top">
        <span className="intent__label" id={labelId}>
          Intent{required && <span className="intent__req"> *</span>}
        </span>
        <span className={`intent__value${current ? ` intent__value--${current.key}` : ""}`}>
          {current ? `${current.label} · ${current.hint}` : "Not set"}
        </span>
      </div>
      <div
        id={id}
        className={`intent-slider${error ? " has-error" : ""}${disabled ? " is-disabled" : ""}`}
        role="slider"
        tabIndex={disabled ? -1 : 0}
        aria-labelledby={labelId}
        aria-valuemin={0}
        aria-valuemax={INTENT_OPTIONS.length - 1}
        // role=slider needs a value: while nothing is chosen it sits mid-bar and reads "Not set".
        aria-valuenow={index >= 0 ? index : 1}
        aria-valuetext={current ? current.label : "Not set"}
        aria-required={required || undefined}
        aria-invalid={error ? true : undefined}
        aria-disabled={disabled || undefined}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => {
          gesture.current = null;
        }}
        onKeyDown={onKeyDown}
      >
        <div className="intent-slider__track" ref={trackRef}>
          {INTENT_OPTIONS.map((option, i) => (
            <span
              key={option.key}
              className="intent-slider__stop"
              style={{ left: `${(i / (INTENT_OPTIONS.length - 1)) * 100}%` }}
            />
          ))}
          {index >= 0 && (
            <span
              className="intent-slider__thumb"
              style={{ left: `${(index / (INTENT_OPTIONS.length - 1)) * 100}%` }}
            />
          )}
        </div>
        <div className="intent-slider__labels" aria-hidden="true">
          {INTENT_OPTIONS.map((option, i) => (
            <span key={option.key} className={i === index ? "is-on" : undefined}>
              {option.label}
            </span>
          ))}
        </div>
      </div>
      {error ? (
        <span className="intent__error" role="alert">{error}</span>
      ) : hint ? (
        <span className="intent__hint">{hint}</span>
      ) : null}
    </div>
  );
}
