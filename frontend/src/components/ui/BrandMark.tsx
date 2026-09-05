interface BrandMarkProps {
  /** sm = sidebar/inline, md = login card, lg = full-screen loader (stacked). */
  size?: "sm" | "md" | "lg";
  /** Use on a dark surface (navy sidebar) — makes the wordmark white. */
  onDark?: boolean;
  className?: string;
}

/**
 * The single FlexCRM brand lockup: an amber gradient "F" chip + the FlexCRM
 * wordmark. One component so login, the loading screen, the pre-load splash, and
 * the sidebar all show the same mark. Styles live in global.css (.brand-mark*).
 */
export function BrandMark({ size = "md", onDark = false, className }: BrandMarkProps) {
  return (
    <span
      className={["brand-mark", `brand-mark--${size}`, onDark ? "brand-mark--on-dark" : null, className]
        .filter(Boolean)
        .join(" ")}
    >
      <span className="brand-mark__chip" aria-hidden="true">F</span>
      <span className="brand-mark__word">
        Flex<span>CRM</span>
      </span>
    </span>
  );
}
