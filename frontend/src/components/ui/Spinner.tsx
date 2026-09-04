interface SpinnerProps {
  size?: "sm" | "lg";
  label?: string;
}


export function Spinner({ size, label }: SpinnerProps) {
  const classes = ["spinner"];
  if (size === "lg") {
    classes.push("spinner--lg");
  }
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
      <span className={classes.join(" ")} aria-hidden />
      {label && <span className="muted text-sm">{label}</span>}
    </span>
  );
}


export function LoadingBlock({
  label = "Loading…",
  slow = false,
  slowLabel = "Waking the server, one moment…"
}: {
  label?: string;
  /** When true (a fetch running unusually long — likely a cold backend), show
   * the reassuring `slowLabel` instead of the generic label. */
  slow?: boolean;
  slowLabel?: string;
}) {
  return (
    <div className="loading-block">
      <Spinner label={slow ? slowLabel : label} />
    </div>
  );
}
