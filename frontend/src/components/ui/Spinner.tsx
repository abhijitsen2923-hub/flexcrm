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


export function LoadingBlock({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading-block">
      <Spinner label={label} />
    </div>
  );
}
