"use client";

import { cn } from "@/lib/cn";

export type StudioTabItem<T extends string = string> = {
  id: T;
  label: string;
  hint?: string;
  testId?: string;
};

export function StudioTabRail<T extends string>({
  items,
  value,
  onChange,
  locked,
  testId,
  ariaLabel,
  tone = "child",
}: {
  items: StudioTabItem<T>[];
  value: T;
  onChange: (id: T) => void;
  locked?: boolean;
  testId?: string;
  ariaLabel: string;
  tone?: "parent" | "child";
}) {
  const cols =
    items.length <= 3
      ? "grid-cols-1 sm:grid-cols-3"
      : items.length <= 4
        ? "grid-cols-2 lg:grid-cols-4"
        : "grid-cols-2 sm:grid-cols-4 xl:grid-cols-8";

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      data-testid={testId}
      className={cn(
        "grid w-full gap-1 rounded-skeuo-md border border-surface-border-subtle p-1",
        tone === "parent" ? "skeuo-panel" : "skeuo-inset bg-surface-panel-inset"
      )}
    >
      <div className={cn("grid w-full gap-1", cols)}>
        {items.map((item) => {
          const selected = value === item.id;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={selected}
              data-testid={item.testId}
              disabled={locked}
              onClick={() => onChange(item.id)}
              className={cn(
                "min-w-0 w-full rounded-skeuo-sm px-2.5 py-2 text-left transition-colors disabled:opacity-50",
                selected
                  ? "skeuo-btn-primary border-transparent text-white"
                  : tone === "parent"
                    ? "text-text-muted hover:bg-surface-raised"
                    : "text-text-muted hover:bg-surface-raised"
              )}
            >
              <span className="block truncate text-[11px] font-semibold uppercase tracking-wide">{item.label}</span>
              {item.hint ? (
                <span
                  className={cn(
                    "mt-0.5 block text-[10px] leading-snug",
                    selected ? "text-white/80" : "text-text-subtle"
                  )}
                >
                  {item.hint}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
