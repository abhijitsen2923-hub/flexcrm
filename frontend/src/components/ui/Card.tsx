import type { PropsWithChildren, ReactNode } from "react";


interface CardProps extends PropsWithChildren {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  className?: string;
}


export function Card({ title, subtitle, actions, children, className }: CardProps) {
  return (
    <section className={["card", className].filter(Boolean).join(" ")}>
      {(title || actions) && (
        <header className="card__header">
          <div>
            {title && <div className="card__title">{title}</div>}
            {subtitle && <div className="card__subtitle">{subtitle}</div>}
          </div>
          {actions && <div className="row">{actions}</div>}
        </header>
      )}
      <div className="card__body">{children}</div>
    </section>
  );
}
