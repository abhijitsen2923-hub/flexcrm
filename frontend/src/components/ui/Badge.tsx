import type { ReactNode } from "react";


type BadgeTone = "neutral" | "primary" | "success" | "warning" | "danger" | "info";

interface BadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
}


export function Badge({ tone = "neutral", children }: BadgeProps) {
  const classes = ["badge"];
  if (tone !== "neutral") {
    classes.push(`badge--${tone}`);
  }
  return <span className={classes.join(" ")}>{children}</span>;
}
