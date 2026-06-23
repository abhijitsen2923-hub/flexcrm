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
