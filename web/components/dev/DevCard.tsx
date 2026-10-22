"use client";

import type { ReactNode } from "react";

export function DevCard({
  title,
  description,
  actions,
  children,
  className = "",
  delayMs = 0,
}: {
  title?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  delayMs?: number;
}) {
  return (
    <article
      className={`dev-card-enter card-surface p-6 ${className}`}
      style={{ animationDelay: `${delayMs}ms` }}
    >
      {(title || actions) && (
        <div className="flex items-start justify-between gap-4">
          <div>
            {title && <h3 className="text-lg font-semibold text-text">{title}</h3>}
            {description && <p className="mt-1 text-sm text-text-muted">{description}</p>}
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </div>
      )}
      {!title && !actions && description && (
        <p className="mt-1 text-sm text-text-muted">{description}</p>
      )}
      {children && <div className={title || description || actions ? "mt-4" : ""}>{children}</div>}
    </article>
  );
}
