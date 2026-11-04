"use client";

import { useEffect, useState } from "react";
import { SkeuoButton } from "@/components/ui/skeuo";
import { adminAction, devFetch } from "@/lib/useAdminResource";
import { cn } from "@/lib/cn";
import { Field, Modal, Notice, TextInput } from "./ui";
import { WorkspacePicker } from "./dialogs";

type Candidate = {
  e164: string;
  provider: string;
  country: string;
  region?: string | null;
  carrierSetupFee?: number | null;
  carrierMonthlyFee?: number | null;
  carrierCurrency?: string | null;
  minimumCommitmentMonths?: number | null;
  monthlyUsd: number;
  monthlyInr: number;
};

type Balance = { available: boolean; balance?: string; currency?: string } | null;

type SearchResult = { numbers: Candidate[]; provider: string; country: string; balance?: Balance };

function fee(value: number | null | undefined, currency: string | null | undefined) {
  if (value === null || value === undefined) return "—";
  const symbol = (currency || "INR").toUpperCase() === "INR" ? "₹" : `${currency} `;
  return `${symbol}${value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

/** What the carrier debits on purchase: setup plus the first month, when it tells us both. */
function dueNow(c: Candidate): number | null {
  if (c.carrierSetupFee == null && c.carrierMonthlyFee == null) return null;
  return (c.carrierSetupFee ?? 0) + (c.carrierMonthlyFee ?? 0);
}

/**
 * Search the active carrier's unassigned inventory and buy one number, either into
 * the platform inventory (to sell to workspaces later) or straight into a workspace.
 *
 * A paid order is irreversible, so it is a 3-step flow: pick a number, review the
 * charge and destination, then type the last four digits to confirm.
 */
export function BuyNumberPanel({
  provider,
  presetTenantId,
  lockTenant = false,
  onBought,
}: {
  provider: string;
  presetTenantId?: string | null;
  lockTenant?: boolean;
  onBought: () => void;
}) {
  const [country, setCountry] = useState(provider === "vobiz" ? "IN" : "US");
  const [contains, setContains] = useState("");
  const [results, setResults] = useState<Candidate[] | null>(null);
  const [balance, setBalance] = useState<Balance>(null);
  const [picked, setPicked] = useState<Candidate | null>(null);
  const [destination, setDestination] = useState<"inventory" | "workspace">(presetTenantId ? "workspace" : "inventory");
  const [tenantId, setTenantId] = useState(presetTenantId ?? "");
  const [reason, setReason] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => setCountry(provider === "vobiz" ? "IN" : "US"), [provider]);
  useEffect(() => {
    if (lockTenant) {
      setTenantId(presetTenantId ?? "");
      // The "add to a workspace" dialog never buys into inventory, even before a
      // workspace is chosen: the buy button waits for one instead.
      setDestination("workspace");
    }
  }, [lockTenant, presetTenantId]);

  async function search() {
    setBusy(true);
    setError(null);
    setDone(null);
    setPicked(null);
    try {
      const q = new URLSearchParams({ provider, country: country.trim().toUpperCase(), limit: "30" });
      const digits = contains.replace(/\D+/g, "");
      if (digits) q.set("contains", digits);
      const res = (await devFetch(`/api/dev/admin/numbers/carrier-search?${q}`)) as SearchResult;
      setResults(res.numbers ?? []);
      setBalance(res.balance ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
      setResults(null);
    } finally {
      setBusy(false);
    }
  }

  const last4 = picked ? picked.e164.slice(-4) : "";
  const charge = picked ? dueNow(picked) : null;
  const balanceNum = balance?.available ? Number(balance.balance) : null;
  const shortOfFunds = charge !== null && balanceNum !== null && Number.isFinite(balanceNum) && balanceNum < charge;
  const needsTenant = destination === "workspace" && !tenantId;
  const canBuy = Boolean(picked) && !busy && !needsTenant && reason.trim().length >= 8 && confirm.trim() === last4 && !shortOfFunds;

  async function buy() {
    if (!picked) return;
    setBusy(true);
    setError(null);
    try {
      const res = await adminAction<{ provisioning?: boolean; destination?: string }>("/api/dev/admin/numbers/carrier-purchase", {
        method: "POST",
        body: {
          e164: picked.e164,
          confirmE164: picked.e164,
          provider: picked.provider,
          country: picked.country,
          tenantId: destination === "workspace" ? tenantId : null,
          reason: reason.trim(),
        },
      });
      const where = res.destination === "inventory" ? "the platform inventory, ready to sell to workspaces" : "the workspace";
      setDone(
        res.provisioning
          ? `${picked.e164} was ordered. The carrier has not confirmed the line yet; it shows as pending until it does. Do not order it again.`
          : `${picked.e164} is bought and added to ${where}.`
      );
      setResults((cur) => (cur ?? []).filter((c) => c.e164 !== picked.e164));
      setPicked(null);
      setConfirm("");
      setReason("");
      onBought();
    } catch (e) {
      setError(e instanceof Error ? e.message : "The order failed. Nothing was added.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {/* Step 1: search */}
      <div className="grid grid-cols-[90px_1fr_auto] items-end gap-2">
        <Field label="Country">
          <TextInput value={country} maxLength={2} onChange={(e) => setCountry(e.target.value.toUpperCase())} className="font-mono" aria-label="Country code" />
        </Field>
        <Field label="Number contains (optional)">
          <TextInput
            value={contains}
            inputMode="numeric"
            maxLength={15}
            onChange={(e) => setContains(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void search();
            }}
            placeholder="e.g. 80 for Bengaluru, 7965 for Ahmedabad"
            className="font-mono"
          />
        </Field>
        <SkeuoButton variant="secondary" loading={busy && !picked} disabled={busy || country.trim().length !== 2} onClick={() => void search()}>
          Search {provider.toUpperCase()}
        </SkeuoButton>
      </div>

      {results !== null && results.length === 0 && <Notice>No unassigned numbers match. Try fewer digits or another country.</Notice>}

      {results !== null && results.length > 0 && (
        <div className="max-h-64 overflow-y-auto rounded-skeuo-sm border border-surface-border-subtle">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-surface-panel text-left text-[10px] uppercase tracking-wider text-text-subtle">
              <tr>
                <th className="px-3 py-2 font-medium">Number</th>
                <th className="px-3 py-2 font-medium">Region</th>
                <th className="px-3 py-2 text-right font-medium">Setup</th>
                <th className="px-3 py-2 text-right font-medium">Monthly</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border-subtle">
              {results.map((c) => {
                const on = picked?.e164 === c.e164;
                return (
                  <tr
                    key={c.e164}
                    onClick={() => {
                      setPicked(c);
                      setConfirm("");
                      setDone(null);
                      setError(null);
                    }}
                    className={cn("cursor-pointer", on ? "bg-accent-primary/10" : "hover:bg-surface-panel-inset")}
                    aria-selected={on}
                  >
                    <td className="px-3 py-2 font-mono">
                      <label className="flex cursor-pointer items-center gap-2">
                        <input type="radio" name="buy-number" checked={on} onChange={() => setPicked(c)} aria-label={`Choose ${c.e164}`} />
                        {c.e164}
                      </label>
                    </td>
                    <td className="px-3 py-2 text-xs text-text-muted">{c.region || "—"}</td>
                    <td className="px-3 py-2 text-right font-mono text-xs">{fee(c.carrierSetupFee, c.carrierCurrency)}</td>
                    <td className="px-3 py-2 text-right font-mono text-xs">{fee(c.carrierMonthlyFee, c.carrierCurrency)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Step 2: review */}
      {picked && (
        <div className="space-y-3 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset p-3">
          <p className="text-xs font-semibold text-text">Review the order</p>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <dt className="text-text-muted">Number</dt>
            <dd className="font-mono">{picked.e164}</dd>
            <dt className="text-text-muted">Region</dt>
            <dd>{picked.region || "—"}</dd>
            <dt className="text-text-muted">Charged now by {picked.provider.toUpperCase()}</dt>
            <dd className="font-mono">{charge === null ? "Shown by the carrier at checkout" : `${fee(charge, picked.carrierCurrency)} (setup + first month)`}</dd>
            <dt className="text-text-muted">Then every month</dt>
            <dd className="font-mono">{fee(picked.carrierMonthlyFee, picked.carrierCurrency)}</dd>
            {picked.minimumCommitmentMonths ? (
              <>
                <dt className="text-text-muted">Minimum commitment</dt>
                <dd>{picked.minimumCommitmentMonths} months</dd>
              </>
            ) : null}
            <dt className="text-text-muted">{picked.provider.toUpperCase()} balance</dt>
            <dd className={cn("font-mono", shortOfFunds && "text-status-error")}>
              {balance?.available ? fee(Number(balance.balance), balance.currency) : "Unknown"}
            </dd>
          </dl>
          {shortOfFunds && (
            <Notice tone="error">The {picked.provider.toUpperCase()} balance is lower than the amount charged now. Top up the carrier account first.</Notice>
          )}

          {!lockTenant && (
            <fieldset className="space-y-1.5 text-xs">
              <legend className="mb-1 font-medium text-text-muted">Add the number to</legend>
              <label className="flex items-start gap-2">
                <input type="radio" name="buy-dest" checked={destination === "inventory"} onChange={() => setDestination("inventory")} className="mt-0.5" />
                <span>
                  <span className="font-medium text-text">Platform inventory</span>
                  <span className="block text-text-subtle">
                    Kept on the platform&apos;s main account as stock. Verified workspaces see it when they buy a number, or you
                    can give it to one with Assign number. Takes no calls until a workspace owns it.
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-2">
                <input type="radio" name="buy-dest" checked={destination === "workspace"} onChange={() => setDestination("workspace")} className="mt-0.5" />
                <span>
                  <span className="font-medium text-text">A specific workspace</span>
                  <span className="block text-text-subtle">
                    Active in that workspace right away, still on the platform&apos;s main account. The workspace must have passed
                    phone-service verification and is not charged for this order.
                  </span>
                </span>
              </label>
            </fieldset>
          )}
          {destination === "workspace" && !lockTenant && <WorkspacePicker value={tenantId} onChange={(id) => setTenantId(id)} label="Workspace" />}
          {lockTenant && needsTenant && <Notice tone="warning">Choose the workspace above first.</Notice>}

          <Field label="Reason (8+ characters)" hint="Recorded in the admin activity log.">
            <TextInput value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} placeholder="e.g. Stock for Bengaluru customers" />
          </Field>
          <Field label={`Type the last 4 digits (${last4}) to confirm`} hint="This is a paid order and cannot be undone. Releasing a number later has a carrier fee.">
            <TextInput value={confirm} inputMode="numeric" maxLength={4} onChange={(e) => setConfirm(e.target.value.replace(/\D+/g, ""))} className="font-mono" aria-label="Confirm last four digits" />
          </Field>
          <div className="flex justify-end gap-2">
            <SkeuoButton variant="ghost" disabled={busy} onClick={() => setPicked(null)}>
              Back
            </SkeuoButton>
            <SkeuoButton variant="primary" loading={busy} disabled={!canBuy} onClick={() => void buy()}>
              Buy {picked.e164}
            </SkeuoButton>
          </div>
        </div>
      )}

      {done && <Notice tone="success">{done}</Notice>}
      {error && <Notice tone="error">{error}</Notice>}
    </div>
  );
}

export function BuyNumbersDialog({ open, provider, onClose }: { open: boolean; provider: string; onClose: (changed: boolean) => void }) {
  const [changed, setChanged] = useState(false);
  const [key, setKey] = useState(0);
  useEffect(() => {
    if (open) {
      setChanged(false);
      setKey((k) => k + 1);
    }
  }, [open]);
  return (
    <Modal open={open} title={`Buy numbers from ${provider.toUpperCase()}`} onClose={() => onClose(changed)} wide>
      <p className="text-xs text-text-muted">
        Search the carrier&apos;s unassigned numbers, pick one, review the charge and confirm. Only numbers the carrier really sells you
        are shown, and the order is placed on the platform&apos;s {provider.toUpperCase()} account.
      </p>
      <BuyNumberPanel key={key} provider={provider} onBought={() => setChanged(true)} />
      <div className="flex justify-end">
        <SkeuoButton variant="ghost" onClick={() => onClose(changed)}>
          {changed ? "Done" : "Close"}
        </SkeuoButton>
      </div>
    </Modal>
  );
}

type Stale = { numberId: string; e164: string; provider: string; hasCarrierId: boolean; createdAt: string | null };

/** Lists pool numbers the carrier account does not own, then removes them on confirmation. */
export function InventoryCheckDialog({ open, onClose }: { open: boolean; onClose: (changed: boolean) => void }) {
  const [stale, setStale] = useState<Stale[] | null>(null);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [removed, setRemoved] = useState<number | null>(null);

  useEffect(() => {
    if (!open) return;
    setStale(null);
    setRemoved(null);
    setError(null);
    setBusy(true);
    adminAction<{ stale: Stale[]; skippedProviders: string[] }>("/api/dev/admin/numbers/inventory/reconcile", { body: { apply: false } })
      .then((r) => {
        setStale(r.stale);
        setSkipped(r.skippedProviders ?? []);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not check the carriers"))
      .finally(() => setBusy(false));
  }, [open]);

  async function apply() {
    setBusy(true);
    setError(null);
    try {
      const r = await adminAction<{ stale: Stale[] }>("/api/dev/admin/numbers/inventory/reconcile", { body: { apply: true } });
      setRemoved(r.stale.length);
      setStale([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove the numbers");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} title="Check inventory against the carriers" onClose={() => onClose(removed !== null && removed > 0)}>
      <p className="text-xs text-text-muted">
        Compares unassigned platform-inventory numbers with the numbers each carrier account really owns. Numbers assigned to a
        workspace are never touched.
      </p>
      {busy && stale === null && <Notice>Asking the carriers…</Notice>}
      {skipped.length > 0 && (
        <Notice tone="warning">Could not reach {skipped.map((s) => s.toUpperCase()).join(", ")}; its numbers were left as they are.</Notice>
      )}
      {stale !== null && stale.length === 0 && removed === null && <Notice tone="success">Every inventory number is on the carrier account.</Notice>}
      {stale !== null && stale.length > 0 && (
        <>
          <Notice tone="warning">
            {stale.length} inventory number{stale.length === 1 ? " is" : "s are"} not on the carrier account. They cannot take calls and
            must not be sold.
          </Notice>
          <ul className="max-h-48 divide-y divide-surface-border-subtle overflow-y-auto rounded-skeuo-sm border border-surface-border-subtle text-xs">
            {stale.map((s) => (
              <li key={s.numberId} className="flex justify-between px-3 py-1.5">
                <span className="font-mono">{s.e164}</span>
                <span className="text-text-muted">
                  {s.provider.toUpperCase()} · {s.hasCarrierId ? "carrier no longer has it" : "never bought on the carrier"}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      {removed !== null && <Notice tone="success">Removed {removed} number{removed === 1 ? "" : "s"} from inventory. Their history is kept.</Notice>}
      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex justify-end gap-2">
        <SkeuoButton variant="ghost" onClick={() => onClose(removed !== null && removed > 0)}>
          {removed !== null ? "Done" : "Cancel"}
        </SkeuoButton>
        {stale !== null && stale.length > 0 && (
          <SkeuoButton variant="primary" loading={busy} onClick={() => void apply()}>
            Remove {stale.length} from inventory
          </SkeuoButton>
        )}
      </div>
    </Modal>
  );
}
