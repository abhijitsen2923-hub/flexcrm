import type { ButtonHTMLAttributes, ReactNode } from "react";


type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "md" | "sm";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
  loading?: boolean;
}


export function Button({
  variant = "primary",
  size = "md",
  icon,
  loading = false,
  disabled,
  className,
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  const classes = ["btn", `btn--${variant}`, size === "sm" ? "btn--sm" : null, className]
    .filter(Boolean)
    .join(" ");

  return (
    <button {...rest} type={type} className={classes} disabled={disabled || loading}>
      {loading ? <span className="spinner" /> : icon}
      {children}
    </button>
  );
}
