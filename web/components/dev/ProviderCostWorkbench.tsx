"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { DevCard } from "@/components/dev/DevCard";
import { Button } from "@/components/ui/Button";
import { adminAction, useAdminResource } from "@/lib/useAdminResource";

type SupplierRate = {
  id: string;
  stage: "stt" | "llm" | "tts";
  provider: string;
  model: string;
  currency: "INR" | "USD";
  unit: string;
  price: string;
  effectiveFrom: string;
  effectiveUntil: string | null;
  sourceUrl: string;
};
type StackCost = {
  tier: string;
  label: string;
  stages: Record<string, { provider: string; model: string }>;
  rateIds: string[];
  costStatus: string;
  missingRates: string[];
  ttsAlternatives?: { provider: string; model: string }[];
};
type ProviderCostSnapshot = {
  schemaVersion: number;
  version: number;
  configured: boolean;
  updatedAt?: string | null;
  rates: SupplierRate[];
  stacks: StackCost[];
};

const UNITS: Record<string, string> = {
  audio_minute: "Audio minute",
  characters_1000: "1,000 characters",
  input_tokens_million: "1M input tokens",
  cached_input_tokens_million: "1M cached input tokens",
  output_tokens_million: "1M output tokens",
  output_audio_tokens_million: "1M output audio tokens",
};
const controlClass = "min-h-11 w-full rounded-lg border border-surface-border bg-surface-raised px-2.5 py-2 text-sm text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40 disabled:opacity-60";

function unitPrice(rate: SupplierRate): string {
  return `${rate.currency === "INR" ? "₹" : "$"}${rate.price} / ${UNITS[rate.unit] || rate.unit}`;
}

export function ProviderCostWorkbench() {
  const resource = useAdminResource<ProviderCostSnapshot>("/api/dev/admin/billing/provider-costs");
  const [draft, setDraft] = useState<SupplierRate[]>([]);
  const [reason, setReason] = useState("");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (!resource.data) return;
    setDraft(resource.data.rates.map((rate) => ({ ...rate })));
    setDirty(false);
  }, [resource.data]);

  function updateRate(index: number, patch: Partial<SupplierRate>) {
    setDraft((current) => current.map((rate, itemIndex) => itemIndex === index ? { ...rate, ...patch } : rate));
    setDirty(true);
    setStatus("");
  }

  async function save() {
    if (!resource.data || busy) return;
    setError("");
    setStatus("");
    if (reason.trim().length < 8) {
      setError("Enter an audit reason of at least 8 characters.");
      return;
    }
    if (draft.some((rate) => !/^\d+(\.\d+)?$/.test(rate.price))) {
      setError("Enter a non-negative decimal price for each supplier rate.");
      return;
    }
    setBusy(true);
    try {
      await adminAction("/api/dev/admin/billing/provider-costs", {
        method: "PUT",
        body: { expectedVersion: resource.data.version, reason: reason.trim(), rates: draft },
      });
      await resource.reload();
      setReason("");
      setStatus("Supplier cost version saved.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save supplier costs. Reload the saved version and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <DevCard title="Low and Standard supplier costs" description="Provider billing units for internal cost attribution. Customer retail prices are managed below.">
      <div className="flex flex-col gap-4" data-testid="provider-cost-workbench">
        {resource.loading && <p className="text-sm text-text-muted">Loading supplier rate version…</p>}
        {(resource.error || error) && <div role="alert" className="text-sm text-warning">
          <p>{error || resource.error}</p>
          <Button type="button" variant="secondary" disabled={busy} className="mt-2" onClick={() => { setError(""); void resource.reload(); }}>Reload saved costs</Button>
        </div>}
        {status && <p role="status" className="text-sm text-text-muted">{status}</p>}
        {resource.data && <>
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-text-muted">
            <p>{resource.data.configured ? `Saved version ${resource.data.version}` : "Published reference rates · not saved as an approved version"}</p>
            <Link href="/dev/stack" className="text-text underline underline-offset-4">Manage voice profiles</Link>
          </div>
          <div className="grid gap-4 lg:grid-cols-2" aria-label="Supplier cost units by stack">
            {resource.data.stacks.filter((stack) => stack.tier !== "premium").map((stack) => (
              <section key={stack.tier} className="rounded-xl border border-surface-border-subtle p-4" data-testid={`supplier-stack-${stack.tier}`}>
                <h3 className="font-medium text-text">{stack.label}</h3>
                <p className="mt-1 text-xs text-text-muted">{stack.costStatus === "ready" ? "Supplier unit rates available" : "Supplier cost configuration incomplete"}</p>
                <dl className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 text-xs">
                  {Object.entries(stack.stages).map(([stage, selection]) => <div key={stage} className="contents">
                    <dt className="uppercase text-text-muted">{stage}</dt><dd className="break-words font-mono text-text">{selection.provider} · {selection.model}</dd>
                  </div>)}
                </dl>
                {(stack.ttsAlternatives?.length || 0) > 1 && <p className="mt-2 text-xs text-text-muted">Other speech models: {stack.ttsAlternatives?.slice(1).map((selection) => `${selection.provider} · ${selection.model}`).join(", ")}</p>}
                <ul className="mt-3 flex flex-col gap-1 text-xs text-text-muted">
                  {resource.data?.rates.filter((rate) => stack.rateIds.includes(rate.id)).map((rate) => <li key={rate.id}>{rate.stage.toUpperCase()} · {unitPrice(rate)}</li>)}
                </ul>
                {stack.missingRates.length > 0 && <ul className="mt-3 flex flex-col gap-1 text-xs text-warning">{stack.missingRates.map((missing) => <li key={missing}>{missing}</li>)}</ul>}
              </section>
            ))}
          </div>
          <p className="text-xs text-text-muted">Speech, text and audio tokens use different billing units. A combined cost per call minute requires measured usage. Dates use UTC; the end date is excluded. Premium 3.8 Live uses its existing cost configuration.</p>
          <div className="overflow-x-auto rounded-xl border border-surface-border-subtle">
            <table className="w-full min-w-[1080px] border-collapse text-left text-xs">
              <caption className="sr-only">Versioned supplier unit rates for Low and Standard voice stages</caption>
              <thead className="bg-surface-raised text-text-muted"><tr>{["Provider / model", "Stage / unit", "Price", "Valid from", "Valid until", "Source"].map((label) => <th key={label} className="whitespace-nowrap px-3 py-3 font-medium">{label}</th>)}</tr></thead>
              <tbody>{draft.map((rate, index) => <tr key={rate.id} className="border-t border-surface-border-subtle align-top">
                <td className="min-w-56 p-3"><label className="flex flex-col gap-1"><span className="sr-only">Provider for rate {index + 1}</span>
                  <select className={controlClass} value={rate.provider} disabled={busy} onChange={(event) => updateRate(index, { provider: event.target.value })}><option value="sarvam">Sarvam</option><option value="gemini">Gemini</option></select></label>
                  <input aria-label={`Model for rate ${index + 1}`} className={`${controlClass} mt-2 font-mono`} value={rate.model} disabled={busy} onChange={(event) => updateRate(index, { model: event.target.value })} /></td>
                <td className="min-w-52 p-3"><select aria-label={`Stage for rate ${index + 1}`} className={controlClass} value={rate.stage} disabled={busy} onChange={(event) => { const stage = event.target.value; if (stage === "stt" || stage === "llm" || stage === "tts") updateRate(index, { stage }); }}>{["stt", "llm", "tts"].map((stage) => <option key={stage} value={stage}>{stage.toUpperCase()}</option>)}</select>
                  <select aria-label={`Unit for rate ${index + 1}`} className={`${controlClass} mt-2`} value={rate.unit} disabled={busy} onChange={(event) => updateRate(index, { unit: event.target.value })}>{Object.entries(UNITS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></td>
                <td className="min-w-36 p-3"><select aria-label={`Currency for rate ${index + 1}`} className={controlClass} value={rate.currency} disabled={busy} onChange={(event) => updateRate(index, { currency: event.target.value === "USD" ? "USD" : "INR" })}><option value="INR">INR ₹</option><option value="USD">USD $</option></select>
                  <input aria-label={`Price for rate ${index + 1}`} inputMode="decimal" className={`${controlClass} mt-2 font-mono`} value={rate.price} disabled={busy} onChange={(event) => updateRate(index, { price: event.target.value })} /></td>
                <td className="p-3"><input type="date" aria-label={`Start date for rate ${index + 1}`} className={controlClass} value={rate.effectiveFrom} disabled={busy} onChange={(event) => updateRate(index, { effectiveFrom: event.target.value })} /></td>
                <td className="p-3"><input type="date" aria-label={`End date for rate ${index + 1}`} className={controlClass} value={rate.effectiveUntil || ""} disabled={busy} onChange={(event) => updateRate(index, { effectiveUntil: event.target.value || null })} /><span className="mt-1 block text-text-subtle">Blank = ongoing</span></td>
                <td className="min-w-52 p-3"><input type="url" aria-label={`Source URL for rate ${index + 1}`} className={controlClass} value={rate.sourceUrl} disabled={busy} onChange={(event) => updateRate(index, { sourceUrl: event.target.value })} />
                  {rate.sourceUrl.startsWith("https://") && <a href={rate.sourceUrl} target="_blank" rel="noreferrer" className="mt-2 inline-block text-text-muted underline">Official source</a>}</td>
              </tr>)}</tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-60 flex-1 text-xs text-text-muted">Audit reason<input value={reason} disabled={busy} onChange={(event) => setReason(event.target.value)} className={`${controlClass} mt-1`} placeholder="Reason for this supplier cost version" /></label>
            <Button type="button" disabled={!dirty || busy} onClick={() => void save()}>{busy ? "Saving supplier costs…" : "Save supplier costs"}</Button>
          </div>
        </>}
      </div>
    </DevCard>
  );
}
