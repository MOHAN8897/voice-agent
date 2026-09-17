"use client";

import { Button } from "@/components/ui/Button";

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  discardLabel = "Discard",
  variant = "primary",
  busy = false,
  onConfirm,
  onCancel,
  onDiscard,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  discardLabel?: string;
  variant?: "primary" | "secondary";
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  onDiscard?: () => void;
}) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
    >
      <div className="w-full max-w-md rounded-2xl border border-surface-border bg-surface-elevated p-6 shadow-card">
        <h2 id="confirm-title" className="text-lg font-semibold text-text">{title}</h2>
        <p className="mt-2 text-sm text-text-muted">{description}</p>
        <div className="mt-6 flex flex-wrap items-center justify-end gap-3">
          {onDiscard ? (
            <Button type="button" variant="ghost" disabled={busy} className="mr-auto" onClick={onDiscard}>
              {discardLabel}
            </Button>
          ) : null}
          <Button type="button" variant="ghost" disabled={busy} onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button type="button" variant={variant} disabled={busy} onClick={onConfirm}>
            {busy ? "Saving…" : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
