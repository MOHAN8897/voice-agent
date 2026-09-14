"use client";

import { cn } from "@/lib/cn";

export const COMPILE_LANGUAGES = [
  { id: "te-IN", label: "Telugu", native: "తెలుగు" },
  { id: "en-IN", label: "English (India)", native: "Indian English" },
  { id: "en-US", label: "English (US/UK)", native: "English" },
  { id: "hi-IN", label: "Hindi", native: "हिन्दी" },
] as const;

export type CompileLanguageId = (typeof COMPILE_LANGUAGES)[number]["id"];

export function compileLanguageLabel(id: string): string {
  return COMPILE_LANGUAGES.find((l) => l.id === id)?.label ?? id;
}

export function CompileLanguagePicker({
  value,
  onChange,
  disabled,
  hint,
  id,
  compact = false,
}: {
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  hint?: string;
  id?: string;
  compact?: boolean;
}) {
  const selected = COMPILE_LANGUAGES.some((l) => l.id === value) ? value : "te-IN";
  const labelId = id ? `${id}-label` : undefined;
  return (
    <div data-testid={id || "compile-language-picker"}>
      <p
        id={labelId}
        className={cn(
          "font-medium text-text-muted",
          compact ? "text-[10px] font-semibold uppercase tracking-wide" : "text-sm"
        )}
      >
        Call language
      </p>
      {hint && !compact ? <p className="mt-0.5 text-[11px] text-text-subtle">{hint}</p> : null}
      <div
        role="radiogroup"
        aria-labelledby={labelId}
        className={cn(
          "flex flex-wrap gap-1 rounded-skeuo-sm border border-surface-border-subtle skeuo-inset p-1",
          compact ? "mt-1.5" : "mt-2"
        )}
      >
        {COMPILE_LANGUAGES.map((lang) => {
          const on = selected === lang.id;
          return (
            <button
              key={lang.id}
              type="button"
              role="radio"
              aria-checked={on}
              data-testid={`compile-language-${lang.id}`}
              disabled={disabled}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                if (disabled) return;
                onChange(lang.id);
              }}
              className={cn(
                "flex-1 rounded-skeuo-sm text-left transition-colors disabled:opacity-50",
                compact ? "min-w-[5.5rem] px-2.5 py-1.5" : "min-w-[7.5rem] px-3 py-2",
                on
                  ? "bg-accent text-accent-fg shadow-skeuo-sm"
                  : "text-text-muted hover:bg-surface-raised"
              )}
            >
              <span className={cn("block font-medium leading-tight", compact ? "text-xs" : "text-sm")}>
                {lang.label}
              </span>
              {!compact ? (
                <span className={cn("mt-0.5 block text-[11px] leading-tight", on ? "opacity-90" : "text-text-subtle")}>
                  {lang.native}
                </span>
              ) : (
                <span className={cn("mt-0.5 block text-[10px] leading-tight", on ? "opacity-90" : "text-text-subtle")}>
                  {lang.native}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {hint && compact ? <p className="mt-1 text-[10px] text-text-subtle">{hint}</p> : null}
    </div>
  );
}
