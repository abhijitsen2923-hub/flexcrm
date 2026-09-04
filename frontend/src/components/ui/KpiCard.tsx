interface KpiCardProps {
  label: string;
  value: string;
  hint?: string;
}

// Shared KPI tile (label + big value + optional hint). Uses the .kpi CSS classes.
export function KpiCard({ label, value, hint }: KpiCardProps) {
  return (
    <div className="kpi">
      <div className="kpi__label">{label}</div>
      <div className="kpi__value">{value}</div>
      {hint && <div className="kpi__hint">{hint}</div>}
    </div>
  );
}
