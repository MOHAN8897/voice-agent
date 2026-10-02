"use client";

import { useEffect, useState, type ReactNode } from "react";
import { SkeuoButton, SkeuoInput } from "@/components/ui/skeuo";

/**
 * Industry-standard admin confirm: statement required before consequential actions.
 * Statement is persisted by the caller (KYC decision, wallet adjust, release, etc.).
 */
export function AdminConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  tone = "default",
  statementLabel = "Admin statement (required)",
  statementPlaceholder = "Why are you taking this action?",
  minLength = 8,
  busy = false,
  children,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  tone?: "default" | "danger";
  statementLabel?: string;
  statementPlaceholder?: string;
  minLength?: number;
  busy?: boolean;
  children?: ReactNode;
  onCancel: () => void;
  onConfirm: (statement: string) => void | Promise<void>;
}) {
  const [statement, setStatement] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setStatement("");
      setLocalError(null);
    }
  }, [open]);

  if (!open) return null;

  async function submit() {
    const text = statement.trim();
    if (text.length < minLength) {
      setLocalError(`Write at least ${minLength} characters explaining this action.`);
      return;
    }
    setLocalError(null);
    await onConfirm(text);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="admin-confirm-title"
      data-testid="admin-confirm-dialog"
    >
      <button
        type="button"
        className="absolute inset-0 bg-black/50"
        aria-label="Dismiss"
        onClick={onCancel}
      />
      <div className="relative z-10 w-full max-w-md rounded-skeuo-md border border-surface-border bg-surface-panel p-5 shadow-lg">
        <h2 id="admin-confirm-title" className="text-base font-semibold text-text">
          {title}
        </h2>
        {description ? <p className="mt-2 text-sm text-text-muted">{description}</p> : null}
        {children ? <div className="mt-3 space-y-2 text-xs text-text-muted">{children}</div> : null}
        <label className="mt-4 block text-xs">
          <span className="mb-1 block text-text-muted">{statementLabel}</span>
          <textarea
            value={statement}
            onChange={(e) => setStatement(e.target.value)}
            placeholder={statementPlaceholder}
            rows={3}
            className="w-full rounded-skeuo-sm border border-surface-border bg-surface-panel-raised px-3 py-2 text-sm text-text"
            data-testid="admin-confirm-statement"
          />
        </label>
        {localError ? (
          <p className="mt-2 text-xs text-status-error" role="alert">
            {localError}
          </p>
        ) : (
          <p className="mt-2 text-[11px] text-text-muted">
            Stored in the audit trail with your admin identity.
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <SkeuoButton type="button" variant="ghost" disabled={busy} onClick={onCancel}>
            Cancel
          </SkeuoButton>
          <SkeuoButton
            type="button"
            disabled={busy}
            onClick={() => void submit()}
            className={tone === "danger" ? "bg-status-error text-white hover:opacity-90" : undefined}
            data-testid="admin-confirm-submit"
          >
            {busy ? "Working…" : confirmLabel}
          </SkeuoButton>
        </div>
      </div>
    </div>
  );
}

/** Lightweight one-line note field for forms that already have a primary action. */
export function AdminStatementField({
  value,
  onChange,
  label = "Admin statement",
}: {
  value: string;
  onChange: (v: string) => void;
  label?: string;
}) {
  return (
    <label className="block text-xs">
      <span className="mb-1 block text-text-muted">{label}</span>
      <SkeuoInput
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Required — why is this change being made?"
        data-testid="admin-statement-field"
      />
    </label>
  );
}
