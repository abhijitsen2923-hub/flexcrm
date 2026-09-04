import "./SkeletonBlock.css";

interface RectProps {
  width?: string;
  height?: string;
  radius?: string;
  className?: string;
}

interface CircleProps {
  size?: string;
  className?: string;
}

export function SkeletonRect({ width = "100%", height = "1rem", radius, className }: RectProps) {
  return (
    <span
      className={["skeleton-rect", className].filter(Boolean).join(" ")}
      style={{ width, height, borderRadius: radius }}
      aria-hidden="true"
    />
  );
}

export function SkeletonCircle({ size = "2rem", className }: CircleProps) {
  return (
    <span
      className={["skeleton-rect", className].filter(Boolean).join(" ")}
      style={{ width: size, height: size, borderRadius: "50%", flexShrink: 0 }}
      aria-hidden="true"
    />
  );
}

/** A full-width card-shaped skeleton placeholder. */
export function SkeletonCard({ rows = 3 }: { rows?: number }) {
  return (
    <div className="skeleton-card" aria-busy="true" aria-label="Loading…">
      <SkeletonRect height="1.1rem" width="60%" />
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonRect key={i} height="0.85rem" width={i % 2 === 0 ? "90%" : "75%"} />
      ))}
    </div>
  );
}

/** A table-shaped placeholder — `rows` lines of `cols` cells. Drop it into the
 * table region while a list loads, keeping the page header/toolbar in place. */
export function SkeletonTable({ rows = 6, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="skeleton-table" aria-busy="true" aria-label="Loading…">
      {Array.from({ length: rows }).map((_, r) => (
        <div
          className="skeleton-table__row"
          key={r}
          style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
        >
          {Array.from({ length: cols }).map((_, c) => (
            <SkeletonRect key={c} height="0.9rem" width={c === 0 ? "45%" : "70%"} />
          ))}
        </div>
      ))}
    </div>
  );
}

/** A row of KPI-card placeholders (dashboard / finance summary headers). */
export function SkeletonKpiRow({ count = 4 }: { count?: number }) {
  return (
    <div className="kpi-grid" aria-busy="true" aria-label="Loading…">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} rows={1} />
      ))}
    </div>
  );
}
