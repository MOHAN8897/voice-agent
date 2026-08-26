import { cn } from "@/lib/cn";

type Material = "panel" | "inset" | "glass" | "chassis";

export function SkeuoPanel({
  children,
  className,
  material = "panel",
  title,
  description,
  headerAction,
  padding = "md",
}: {
  children: React.ReactNode;
  className?: string;
  material?: Material;
  title?: string;
  description?: string;
  headerAction?: React.ReactNode;
  padding?: "none" | "sm" | "md" | "lg";
}) {
  const pad =
    padding === "none"
      ? ""
      : padding === "sm"
        ? "p-3"
        : padding === "lg"
          ? "p-6"
          : "p-4";

  return (
    <section
      className={cn(
        "rounded-skeuo-md border border-surface-border-subtle",
        material === "panel" && "skeuo-panel",
        material === "inset" && "skeuo-inset",
        material === "glass" && "skeuo-glass",
        material === "chassis" && "bg-surface-chassis",
        className
      )}
    >
      {(title || description || headerAction) && (
        <header className="flex items-start justify-between gap-3 border-b border-surface-border-subtle px-4 py-3">
          <div>
            {title && <h2 className="text-sm font-medium tracking-tight text-text">{title}</h2>}
            {description && <p className="mt-0.5 text-xs text-text-muted">{description}</p>}
          </div>
          {headerAction}
        </header>
      )}
      <div className={pad}>{children}</div>
    </section>
  );
}
