"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { SkeuoBadge, SkeuoButton } from "@/components/ui/skeuo";
import { confirmPhrase, type BadgeTone, type BulkResult } from "./model";

/* ------------------------------------------------------------------ form bits */

export const selectClass =
  "w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-2.5 py-2 text-sm text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/30";

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={cn("block text-xs", className)}>
      <span className="mb-1 block font-medium text-text-muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-text-subtle">{hint}</span>}
    </label>
  );
}

export function FilterSelect({
  label,
  value,
  onChange,
  options,
  anyLabel = "Any",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: Array<{ value: string; label: string }>;
  anyLabel?: string;
}) {
  return (
    <Field label={label}>
      <select value={value} onChange={(e) => onChange(e.target.value)} className={selectClass} aria-label={label}>
        <option value="">{anyLabel}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Field>
  );
}

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn(selectClass, props.className)} />;
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warning" | "error" | "success"; children: ReactNode }) {
  const tones = {
    info: "border-surface-border-subtle bg-surface-panel-inset text-text-muted",
    warning: "border-status-warning/30 bg-status-warning/10 text-text",
    error: "border-status-error/30 bg-status-error/10 text-status-error",
    success: "border-status-success/30 bg-status-success/10 text-text",
  } as const;
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cn("rounded-skeuo-sm border px-3 py-2 text-xs leading-relaxed", tones[tone])}>
      {children}
    </div>
  );
}

export function StatusBadge({ tone, children }: { tone: BadgeTone; children: ReactNode }) {
  return <SkeuoBadge tone={tone}>{children}</SkeuoBadge>;
}

/* ------------------------------------------------------------------ data table */

export type Column<T> = {
  id: string;
  label: string;
  sortKey?: string;
  render: (row: T) => ReactNode;
  className?: string;
  /** Columns an operator can hide; the identity column is always shown. */
  hideable?: boolean;
  defaultHidden?: boolean;
};

export type Selection = { ids: Set<string>; allMatching: boolean };

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  error,
  total,
  limit,
  offset,
  sort,
  dir,
  onSort,
  onPage,
  onLimit,
  selection,
  onSelection,
  onOpen,
  isRowSelectable,
  empty,
  storageKey,
  noun,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  loading: boolean;
  error: string | null;
  total: number;
  limit: number;
  offset: number;
  sort: string;
  dir: "asc" | "desc";
  onSort: (key: string) => void;
  onPage: (offset: number) => void;
  onLimit: (limit: number) => void;
  selection: Selection;
  onSelection: (s: Selection) => void;
  onOpen: (row: T) => void;
  isRowSelectable?: (row: T) => boolean;
  empty: ReactNode;
  storageKey: string;
  noun: string;
}) {
  const [hidden, setHidden] = useState<Set<string>>(() => new Set(columns.filter((c) => c.defaultHidden).map((c) => c.id)));
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(`accounts.columns.${storageKey}`);
      if (raw) setHidden(new Set(JSON.parse(raw) as string[]));
    } catch {
      /* per-viewer convenience only */
    }
  }, [storageKey]);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuOpen]);

  function toggleColumn(id: string) {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      try {
        window.localStorage.setItem(`accounts.columns.${storageKey}`, JSON.stringify([...next]));
      } catch {
        /* ignore */
      }
      return next;
    });
  }

  const visible = columns.filter((c) => !hidden.has(c.id));
  const selectableRows = rows.filter((r) => (isRowSelectable ? isRowSelectable(r) : true));
  const pageIds = selectableRows.map(rowKey);
  const pageAllSelected = pageIds.length > 0 && pageIds.every((id) => selection.allMatching || selection.ids.has(id));
  const somePageSelected = pageIds.some((id) => selection.ids.has(id));
  const selectedCount = selection.allMatching ? total : selection.ids.size;

  function togglePage() {
    if (selection.allMatching || pageAllSelected) {
      onSelection({ ids: new Set(), allMatching: false });
    } else {
      const next = new Set(selection.ids);
      pageIds.forEach((id) => next.add(id));
      onSelection({ ids: next, allMatching: false });
    }
  }

  function toggleRow(id: string) {
    if (selection.allMatching) {
      // Leaving "all matching" mode: keep the page minus this row.
      const next = new Set(pageIds.filter((x) => x !== id));
      onSelection({ ids: next, allMatching: false });
      return;
    }
    const next = new Set(selection.ids);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelection({ ids: next, allMatching: false });
  }

  const headerCheckbox = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (headerCheckbox.current) headerCheckbox.current.indeterminate = !pageAllSelected && somePageSelected;
  }, [pageAllSelected, somePageSelected]);

  const pageEnd = Math.min(offset + limit, total);

  return (
    <div className="space-y-2">
      {pageAllSelected && !selection.allMatching && total > pageIds.length && (
        <div className="flex flex-wrap items-center justify-center gap-2 rounded-skeuo-sm border border-accent-primary/30 bg-accent-primary/10 px-3 py-2 text-xs text-text">
          <span>
            All {pageIds.length} {noun} on this page are selected.
          </span>
          <button
            type="button"
            className="font-semibold text-accent-primary underline"
            onClick={() => onSelection({ ids: new Set(), allMatching: true })}
            data-testid="select-all-matching"
          >
            Select all {total} matching {noun}
          </button>
        </div>
      )}
      {selection.allMatching && (
        <div className="flex flex-wrap items-center justify-center gap-2 rounded-skeuo-sm border border-accent-primary/30 bg-accent-primary/10 px-3 py-2 text-xs text-text">
          <span>
            All <strong>{total}</strong> {noun} matching your filters are selected.
          </span>
          <button type="button" className="text-accent-primary underline" onClick={() => onSelection({ ids: new Set(), allMatching: false })}>
            Clear selection
          </button>
        </div>
      )}

      <div className="flex items-center justify-between gap-2 text-xs text-text-muted">
        <span aria-live="polite">
          {loading
            ? "Loading…"
            : total === 0
              ? `No ${noun}`
              : `Showing ${offset + 1}–${pageEnd} of ${total} ${noun}`}
          {selectedCount > 0 && <strong className="ml-2 text-text">· {selectedCount} selected</strong>}
        </span>
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            className="rounded-skeuo-sm border border-surface-border-subtle px-2.5 py-1 text-xs text-text-muted hover:text-text"
            aria-expanded={menuOpen}
          >
            Columns
          </button>
          {menuOpen && (
            <div className="absolute right-0 z-30 mt-1 w-52 rounded-skeuo-md border border-surface-border bg-surface-panel p-2 shadow-lg">
              <p className="px-1 pb-1 text-[10px] uppercase tracking-wider text-text-subtle">Show columns</p>
              {columns
                .filter((c) => c.hideable !== false)
                .map((c) => (
                  <label key={c.id} className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-xs text-text hover:bg-surface-panel-raised">
                    <input type="checkbox" checked={!hidden.has(c.id)} onChange={() => toggleColumn(c.id)} />
                    {c.label}
                  </label>
                ))}
            </div>
          )}
        </div>
      </div>

      {error && <Notice tone="error">{error}</Notice>}

      <div className="overflow-x-auto rounded-skeuo-lg border border-surface-border-subtle skeuo-panel">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="border-b border-surface-border-subtle bg-surface-panel-inset text-text-subtle">
            <tr>
              <th className="w-10 px-3 py-3">
                <input
                  ref={headerCheckbox}
                  type="checkbox"
                  aria-label={`Select all ${noun} on this page`}
                  checked={pageAllSelected}
                  disabled={pageIds.length === 0}
                  onChange={togglePage}
                />
              </th>
              {visible.map((c) => {
                const active = c.sortKey && sort === c.sortKey;
                return (
                  <th
                    key={c.id}
                    className={cn("px-3 py-3 font-mono text-[10px] font-medium uppercase tracking-wider", c.className)}
                    aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : undefined}
                  >
                    {c.sortKey ? (
                      <button
                        type="button"
                        onClick={() => onSort(c.sortKey!)}
                        className={cn("inline-flex items-center gap-1 uppercase hover:text-text", active && "text-text")}
                      >
                        {c.label}
                        <span aria-hidden className="text-[9px]">
                          {active ? (dir === "asc" ? "▲" : "▼") : "↕"}
                        </span>
                      </button>
                    ) : (
                      c.label
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border-subtle">
            {rows.map((row) => {
              const id = rowKey(row);
              const selectable = isRowSelectable ? isRowSelectable(row) : true;
              const checked = selectable && (selection.allMatching || selection.ids.has(id));
              return (
                <tr
                  key={id}
                  className={cn(
                    "cursor-pointer bg-surface-panel transition-colors hover:bg-surface-panel-raised/60",
                    checked && "bg-accent-primary/5"
                  )}
                  onClick={(e) => {
                    const target = e.target as HTMLElement;
                    if (target.closest("input,button,a,select")) return;
                    onOpen(row);
                  }}
                >
                  <td className="px-3 py-2.5">
                    <input
                      type="checkbox"
                      aria-label={`Select ${id}`}
                      checked={checked}
                      disabled={!selectable}
                      title={selectable ? undefined : "Not available for bulk actions"}
                      onChange={() => toggleRow(id)}
                    />
                  </td>
                  {visible.map((c) => (
                    <td key={c.id} className={cn("px-3 py-2.5 align-top", c.className)}>
                      {c.render(row)}
                    </td>
                  ))}
                </tr>
              );
            })}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={visible.length + 1} className="px-4 py-10">
                  {empty}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-text-muted">
        <label className="flex items-center gap-2">
          Rows per page
          <select
            value={limit}
            onChange={(e) => onLimit(Number(e.target.value))}
            className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-2 py-1 text-xs text-text"
          >
            {[10, 25, 50, 100].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-center gap-2">
          <span>
            Page {total === 0 ? 0 : Math.floor(offset / limit) + 1} of {Math.max(1, Math.ceil(total / limit))}
          </span>
          <SkeuoButton size="sm" variant="secondary" disabled={offset <= 0 || loading} onClick={() => onPage(Math.max(0, offset - limit))}>
            Previous
          </SkeuoButton>
          <SkeuoButton size="sm" variant="secondary" disabled={offset + limit >= total || loading} onClick={() => onPage(offset + limit)}>
            Next
          </SkeuoButton>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ selection bar */

export function SelectionBar({
  count,
  noun,
  onClear,
  children,
}: {
  count: number;
  noun: string;
  onClear: () => void;
  children: ReactNode;
}) {
  if (count === 0) return null;
  return (
    <div
      className="sticky top-2 z-20 flex flex-wrap items-center gap-2 rounded-skeuo-md border border-accent-primary/40 bg-surface-panel px-3 py-2 shadow-lg"
      data-testid="bulk-bar"
    >
      <span className="text-sm font-semibold text-text">
        {count} {noun} selected
      </span>
      <button type="button" className="text-xs text-text-muted underline hover:text-text" onClick={onClear}>
        Clear
      </button>
      <span className="mx-1 h-5 w-px bg-surface-border-subtle" aria-hidden />
      <div className="flex flex-wrap items-center gap-1.5">{children}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ dialogs */

export function Modal({
  open,
  title,
  onClose,
  children,
  wide,
  labelledBy = "accounts-modal-title",
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
  labelledBy?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby={labelledBy} data-accounts-modal="">
      <button type="button" className="absolute inset-0 bg-black/50" aria-label="Close" onClick={onClose} />
      <div
        className={cn(
          "relative z-10 max-h-[90vh] w-full overflow-y-auto rounded-skeuo-md border border-surface-border bg-surface-panel p-5 shadow-xl",
          wide ? "max-w-2xl" : "max-w-md"
        )}
      >
        <h2 id={labelledBy} className="text-base font-semibold text-text">
          {title}
        </h2>
        <div className="mt-3 space-y-3">{children}</div>
      </div>
    </div>
  );
}

/**
 * Confirmation for any bulk (or consequential single) action: a written reason
 * always, a typed phrase for destructive ones, then the per-item outcome.
 */
export function ActionDialog({
  open,
  title,
  description,
  action,
  count,
  destructive,
  confirmLabel,
  onClose,
  onRun,
  children,
  canRun = true,
  labelFor,
}: {
  open: boolean;
  title: string;
  description?: ReactNode;
  action: string;
  count: number;
  destructive?: boolean;
  confirmLabel: string;
  onClose: (changed: boolean) => void;
  onRun: (reason: string, confirm: string) => Promise<BulkResult | void>;
  children?: ReactNode;
  canRun?: boolean;
  labelFor?: (id: string) => string;
}) {
  const [reason, setReason] = useState("");
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BulkResult | null>(null);
  const phrase = confirmPhrase(action, count);

  useEffect(() => {
    if (open) {
      setReason("");
      setTyped("");
      setError(null);
      setResult(null);
      setBusy(false);
    }
  }, [open]);

  const ready = reason.trim().length >= 8 && (!destructive || typed.trim().toUpperCase() === phrase) && canRun;

  async function submit() {
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      const res = await onRun(reason.trim(), typed.trim());
      if (res) setResult(res);
      else onClose(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} title={title} onClose={() => !busy && onClose(Boolean(result))} wide={Boolean(result)}>
      {result ? (
        <BulkOutcome result={result} labelFor={labelFor} onDone={() => onClose(true)} />
      ) : (
        <>
          {description && <div className="text-sm text-text-muted">{description}</div>}
          {children}
          <Field label="Reason (saved to the audit log)" hint="At least 8 characters. Stored with your admin identity.">
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={2}
              className={selectClass}
              placeholder="Why are you doing this?"
              data-testid="action-reason"
            />
          </Field>
          {destructive && (
            <Field label={`Type ${phrase} to confirm`}>
              <TextInput
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                placeholder={phrase}
                autoComplete="off"
                data-testid="action-confirm"
              />
            </Field>
          )}
          {error && <Notice tone="error">{error}</Notice>}
          <div className="flex justify-end gap-2 pt-1">
            <SkeuoButton variant="ghost" disabled={busy} onClick={() => onClose(false)}>
              Cancel
            </SkeuoButton>
            <SkeuoButton
              variant="primary"
              disabled={!ready || busy}
              loading={busy}
              onClick={() => void submit()}
              className={destructive ? "!bg-status-error !bg-none" : undefined}
              data-testid="action-submit"
            >
              {confirmLabel}
            </SkeuoButton>
          </div>
        </>
      )}
    </Modal>
  );
}

export function BulkOutcome({ result, labelFor, onDone }: { result: BulkResult; labelFor?: (id: string) => string; onDone: () => void }) {
  const label = (id: string) => (labelFor ? labelFor(id) : id.slice(0, 8));
  return (
    <div className="space-y-3" data-testid="bulk-outcome">
      <div className="grid grid-cols-3 gap-2 text-center">
        <OutcomeStat label="Done" value={result.counts.processed} tone="text-status-success" />
        <OutcomeStat label="Skipped" value={result.counts.skipped} tone="text-text-muted" />
        <OutcomeStat label="Failed" value={result.counts.failed} tone={result.counts.failed ? "text-status-error" : "text-text-muted"} />
      </div>
      {result.replayed && <Notice>This request was already processed; showing the earlier result.</Notice>}
      {result.failed.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium text-text">Failed — nothing changed for these</p>
          <ul className="max-h-40 space-y-1 overflow-y-auto text-xs">
            {result.failed.map((f) => (
              <li key={f.id} className="rounded-skeuo-sm bg-status-error/10 px-2 py-1 text-status-error">
                <span className="font-mono">{label(f.id)}</span> — {f.error}
              </li>
            ))}
          </ul>
        </div>
      )}
      {result.skipped.length > 0 && (
        <details className="text-xs text-text-muted">
          <summary className="cursor-pointer">Skipped ({result.skipped.length}) — already in the requested state</summary>
          <ul className="mt-1 max-h-32 space-y-0.5 overflow-y-auto">
            {result.skipped.map((s) => (
              <li key={s.id}>
                <span className="font-mono">{label(s.id)}</span> — {s.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
      <div className="flex justify-end">
        <SkeuoButton variant="primary" onClick={onDone}>
          Done
        </SkeuoButton>
      </div>
    </div>
  );
}

function OutcomeStat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset p-2">
      <p className={cn("font-mono text-xl", tone)}>{value}</p>
      <p className="text-[10px] uppercase tracking-wider text-text-subtle">{label}</p>
    </div>
  );
}

/* ------------------------------------------------------------------ drawer */

export function Drawer({
  open,
  title,
  subtitle,
  badges,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  title: ReactNode;
  subtitle?: ReactNode;
  badges?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      // A dialog opened from the drawer handles its own Escape.
      if (e.key === "Escape" && !document.querySelector("[data-accounts-modal]")) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end" data-testid="accounts-drawer">
      <button type="button" className="absolute inset-0 bg-black/40" aria-label="Close details" onClick={onClose} />
      <aside
        className="relative z-10 flex h-full w-full max-w-xl flex-col border-l border-surface-border bg-surface-chassis shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-label="Details"
      >
        <header className="flex items-start justify-between gap-3 border-b border-surface-border-subtle bg-surface-panel px-5 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold text-text">{title}</h2>
            {subtitle && <div className="mt-0.5 truncate text-xs text-text-muted">{subtitle}</div>}
            {badges && <div className="mt-2 flex flex-wrap gap-1.5">{badges}</div>}
          </div>
          <button type="button" onClick={onClose} className="rounded-skeuo-sm px-2 py-1 text-sm text-text-muted hover:bg-surface-panel-raised hover:text-text" aria-label="Close">
            ✕
          </button>
        </header>
        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="border-t border-surface-border-subtle bg-surface-panel px-5 py-3">{footer}</footer>}
      </aside>
    </div>
  );
}

export function DrawerSection({ title, hint, action, children }: { title: string; hint?: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section>
      <div className="mb-2 flex items-end justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-text">{title}</h3>
          {hint && <p className="text-[11px] text-text-muted">{hint}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function KeyValues({ items }: { items: Array<[string, ReactNode]> }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel p-3 text-xs">
      {items.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className="text-[10px] uppercase tracking-wider text-text-subtle">{k}</dt>
          <dd className="mt-0.5 truncate text-text">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="mx-auto max-w-md text-center">
      <p className="font-medium text-text">{title}</p>
      <p className="mt-1 text-sm text-text-muted">{body}</p>
      {action && <div className="mt-3 flex justify-center gap-2">{action}</div>}
    </div>
  );
}

/** Debounced copy of a value (search boxes). */
export function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function useStableKey(obj: Record<string, unknown>): string {
  return useMemo(() => JSON.stringify(obj), [obj]);
}
