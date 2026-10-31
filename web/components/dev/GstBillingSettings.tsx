"use client";

import { useEffect, useState } from "react";
import { DevCard } from "@/components/dev/DevCard";
import { SkeuoButton, SkeuoInput, SkeuoTextarea } from "@/components/ui/skeuo";
import { adminAction, formatWhen, useAdminResource } from "@/lib/useAdminResource";

type StateOption = { code: string; name: string };

type TaxSettings = {
  enabled: boolean;
  legalName: string;
  tradeName: string;
  gstin: string | null;
  pan: string | null;
  addressLine1: string;
  addressLine2: string;
  city: string;
  stateCode: string;
  stateName: string;
  postalCode: string;
  countryCode: string;
  supportEmail: string;
  supportPhone: string;
  sacCode: string;
  defaultRateBps: number;
  priceIncludesTax: boolean;
  exportZeroRated: boolean;
  invoicePrefix: string;
  creditNotePrefix: string;
  lutNumber: string | null;
  invoiceTerms: string;
  updatedAt?: string | null;
  updatedBy?: string | null;
  configured: boolean;
  ratePercent: number;
  stateOptions: StateOption[];
  currentFy: string;
  webhookConfigured: boolean;
  razorpayConfigured: boolean;
  pdfAvailable: boolean;
};

type FormState = {
  enabled: boolean;
  legalName: string;
  tradeName: string;
  gstin: string;
  pan: string;
  addressLine1: string;
  addressLine2: string;
  city: string;
  stateCode: string;
  postalCode: string;
  supportEmail: string;
  supportPhone: string;
  sacCode: string;
  ratePercent: string;
  priceIncludesTax: boolean;
  exportZeroRated: boolean;
  invoicePrefix: string;
  creditNotePrefix: string;
  lutNumber: string;
  invoiceTerms: string;
};

const EMPTY_FORM: FormState = {
  enabled: false,
  legalName: "",
  tradeName: "",
  gstin: "",
  pan: "",
  addressLine1: "",
  addressLine2: "",
  city: "",
  stateCode: "",
  postalCode: "",
  supportEmail: "",
  supportPhone: "",
  sacCode: "998413",
  ratePercent: "18",
  priceIncludesTax: false,
  exportZeroRated: true,
  invoicePrefix: "INV",
  creditNotePrefix: "CN",
  lutNumber: "",
  invoiceTerms: "",
};

function toForm(data: TaxSettings): FormState {
  return {
    enabled: Boolean(data.enabled),
    legalName: data.legalName || "",
    tradeName: data.tradeName || "",
    gstin: data.gstin || "",
    pan: data.pan || "",
    addressLine1: data.addressLine1 || "",
    addressLine2: data.addressLine2 || "",
    city: data.city || "",
    stateCode: data.stateCode || "",
    postalCode: data.postalCode || "",
    supportEmail: data.supportEmail || "",
    supportPhone: data.supportPhone || "",
    sacCode: data.sacCode || "998413",
    ratePercent: String(data.ratePercent ?? 18),
    priceIncludesTax: Boolean(data.priceIncludesTax),
    exportZeroRated: data.exportZeroRated !== false,
    invoicePrefix: data.invoicePrefix || "INV",
    creditNotePrefix: data.creditNotePrefix || "CN",
    lutNumber: data.lutNumber || "",
    invoiceTerms: data.invoiceTerms || "",
  };
}

function StatusPill({
  ok,
  label,
  hint,
}: {
  ok: boolean;
  label: string;
  hint?: string;
}) {
  return (
    <span
      title={hint}
      className={`inline-flex items-center gap-1.5 rounded-skeuo-sm border px-2.5 py-1 text-[11px] font-semibold ${
        ok
          ? "border-emerald-200 bg-emerald-50 text-emerald-700"
          : "border-amber-200 bg-amber-50 text-amber-800"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-emerald-600" : "bg-amber-500"}`} />
      {label}
    </span>
  );
}

function Field({
  label,
  hint,
  children,
  className = "",
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={`block text-xs ${className}`}>
      <span className="block font-medium text-text-muted">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-[11px] text-text-subtle">{hint}</span> : null}
    </label>
  );
}

export function GstBillingSettings() {
  const settings = useAdminResource<TaxSettings>("/api/dev/admin/payments/tax-settings");
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [loadedSettings, setLoadedSettings] = useState<TaxSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [preview, setPreview] = useState<{total: number; subtotal: number; tax: number; creditInr: number; currency: string; taxKind: string} | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewAmount, setPreviewAmount] = useState("1000");
  const [previewCurrency, setPreviewCurrency] = useState("INR");
  const [previewBuyer, setPreviewBuyer] = useState("same");

  useEffect(() => {
    if (settings.data) {
      setForm(toForm(settings.data));
      setLoadedSettings(settings.data);
    }
  }, [settings.data]);

  const stateOptions = settings.data?.stateOptions ?? [];

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setPreview(null);
  }

  function payload() {
    return {
        enabled: form.enabled,
        legalName: form.legalName,
        tradeName: form.tradeName,
        gstin: form.gstin.trim() ? form.gstin.trim().toUpperCase() : null,
        pan: form.pan.trim() ? form.pan.trim().toUpperCase() : null,
        addressLine1: form.addressLine1,
        addressLine2: form.addressLine2,
        city: form.city,
        stateCode: form.stateCode,
        stateName: stateOptions.find((item) => item.code === form.stateCode)?.name || "",
        postalCode: form.postalCode,
        countryCode: "IN",
        supportEmail: form.supportEmail,
        supportPhone: form.supportPhone,
        sacCode: form.sacCode,
        defaultRateBps: Math.round(Number(form.ratePercent) * 100),
        priceIncludesTax: form.priceIncludesTax,
        exportZeroRated: form.exportZeroRated,
        invoicePrefix: form.invoicePrefix,
        creditNotePrefix: form.creditNotePrefix,
        lutNumber: form.lutNumber.trim() || null,
        invoiceTerms: form.invoiceTerms,
        expectedUpdatedAt: settings.data?.updatedAt || null,
      };
  }

  async function previewCheckout() {
    setPreviewBusy(true); setError(null); setPreview(null);
    try {
      const result = await adminAction("/api/dev/admin/payments/tax-preview", { method: "POST", body: {
        settings: payload(), amount: Number(previewAmount), currency: previewCurrency,
        buyerCountry: previewBuyer === "export" ? "US" : "IN",
        buyerState: previewBuyer === "same" ? form.stateCode : (form.stateCode === "27" ? "36" : "27"),
      } });
      setPreview(result as {total: number; subtotal: number; tax: number; creditInr: number; currency: string; taxKind: string});
    } catch (err) { setError(err instanceof Error ? err.message : "Could not preview checkout."); }
    finally { setPreviewBusy(false); }
  }

  function save() {
    const rate = Number(form.ratePercent);
    if (!Number.isFinite(rate) || rate < 0 || rate > 50) {
      setError("GST rate must be between 0% and 50%.");
      return;
    }
    setBusy(true);
    setError(null);
    setSavedAt(null);
    void adminAction("/api/dev/admin/payments/tax-settings", {
      method: "PUT",
      body: payload(),
    })
      .then(async (result) => {
        setSavedAt(new Date().toISOString());
        await settings.reload();
        return result;
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "Could not save GST settings.");
      })
      .finally(() => setBusy(false));
  }

  const data = settings.data;

  return (
    <DevCard
      title="GST & invoicing"
      description="The tax identity printed on every recharge invoice and credit note. Checkout snapshots these values, so changes only affect future orders."
      actions={
        <div className="flex flex-wrap justify-end gap-2">
          <StatusPill
            ok={Boolean(data?.enabled)}
            label={data?.enabled ? "GST enabled" : "GST off"}
            hint="When off, orders are charged without GST and invoices carry no tax lines."
          />
          <StatusPill
            ok={Boolean(data?.configured)}
            label={data?.configured ? "Invoice identity complete" : "Identity incomplete"}
            hint="A compliant tax invoice needs legal name, address, city, state and a valid GSTIN."
          />
          <StatusPill
            ok={Boolean(data?.webhookConfigured)}
            label={data?.webhookConfigured ? "Webhook configured" : "Webhook secret missing"}
            hint="Without the Razorpay webhook secret, payments are only confirmed by the browser callback."
          />
          <StatusPill
            ok={Boolean(data?.pdfAvailable)}
            label={data?.pdfAvailable ? "PDF ready" : "PDF engine missing"}
            hint="ReportLab is required to render invoice PDFs."
          />
        </div>
      }
    >
      <fieldset id="gst-billing" disabled={busy || settings.loading || !settings.data || loadedSettings !== settings.data} className="min-w-0 space-y-5 pt-1">
        <div className="grid gap-4 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-4 text-xs sm:grid-cols-3">
          <div>
            <span className="block text-text-muted">Current financial year</span>
            <span className="mt-1 block font-mono text-sm font-semibold">{data?.currentFy ?? "—"}</span>
            <span className="mt-1 block text-[11px] text-text-subtle">
              Indian FY (1 April – 31 March, IST). Invoice serials reset each year.
            </span>
          </div>
          <div>
            <span className="block text-text-muted">Invoice series</span>
            <span className="mt-1 block font-mono text-sm font-semibold">
              {form.invoicePrefix || "INV"}/{data?.currentFy ?? "FY"}/…
            </span>
            <span className="mt-1 block text-[11px] text-text-subtle">
              Consecutive per FY, 16 characters maximum (CGST Rule 46(b)).
            </span>
          </div>
          <div>
            <span className="block text-text-muted">Last saved</span>
            <span className="mt-1 block font-mono text-sm font-semibold">
              {savedAt ? "just now" : formatWhen(data?.updatedAt)}
            </span>
            <span className="mt-1 block text-[11px] text-text-subtle">
              {data?.updatedBy ? `by ${data.updatedBy}` : "Tax settings are audited."}
            </span>
          </div>
        </div>

        <label className="flex items-start gap-3 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel p-3 text-xs">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => update("enabled", e.target.checked)}
            className="mt-0.5 h-4 w-4"
            aria-label="Enable GST on new orders"
          />
          <span>
            <span className="block font-semibold text-text">Charge GST on new recharges</span>
            <span className="block text-text-muted">
              Applies to orders created from now on. Existing orders keep the tax snapshot taken at
              checkout. Disable only when the platform is not GST-registered.
            </span>
          </span>
        </label>

        <datalist id="gst-state-options">
          {stateOptions.map((state) => (
            <option key={state.code} value={state.code}>
              {state.name}
            </option>
          ))}
        </datalist>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Legal name" hint="Registered business name, printed as the supplier.">
            <SkeuoInput
              value={form.legalName}
              onChange={(e) => update("legalName", e.target.value)}
              placeholder="Dialtact Technologies Pvt Ltd"
            />
          </Field>
          <Field label="Trade name" hint="Optional brand name shown beneath the legal name.">
            <SkeuoInput
              value={form.tradeName}
              onChange={(e) => update("tradeName", e.target.value)}
              placeholder="Dialtact"
            />
          </Field>
          <Field label="GSTIN" hint="15 characters; the check digit and state prefix are validated.">
            <SkeuoInput
              value={form.gstin}
              onChange={(e) => update("gstin", e.target.value.toUpperCase())}
              maxLength={15}
              placeholder="29ABCDE1234F1Z5"
              className="font-mono"
            />
          </Field>
          <Field label="PAN" hint="Optional, printed on the invoice footer.">
            <SkeuoInput
              value={form.pan}
              onChange={(e) => update("pan", e.target.value.toUpperCase())}
              maxLength={10}
              placeholder="ABCDE1234F"
              className="font-mono"
            />
          </Field>
          <Field label="SAC code" hint="998413 — telecom/voice services.">
            <SkeuoInput
              value={form.sacCode}
              onChange={(e) => update("sacCode", e.target.value)}
              maxLength={12}
              className="font-mono"
            />
          </Field>
          <Field
            label="GST rate (%)"
            hint="18% standard for voice/telecom. Place of supply decides CGST+SGST vs IGST."
          >
            <SkeuoInput
              value={form.ratePercent}
              aria-label="GST rate (%)"
              onChange={(e) => update("ratePercent", e.target.value)}
              inputMode="decimal"
              className="font-mono"
            />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Registered address line 1" className="sm:col-span-2">
            <SkeuoInput
              value={form.addressLine1}
              onChange={(e) => update("addressLine1", e.target.value)}
              placeholder="8th Floor, Prestige Tech Park"
            />
          </Field>
          <Field label="Address line 2" className="sm:col-span-2">
            <SkeuoInput
              value={form.addressLine2}
              onChange={(e) => update("addressLine2", e.target.value)}
              placeholder="Outer Ring Road"
            />
          </Field>
          <Field label="City">
            <SkeuoInput value={form.city} onChange={(e) => update("city", e.target.value)} placeholder="Bengaluru" />
          </Field>
          <Field label="State" hint="The supplier state drives CGST+SGST vs IGST.">
            <select
              value={form.stateCode}
              onChange={(e) => update("stateCode", e.target.value)}
              className="mt-2 w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm text-text shadow-inset"
            >
              <option value="">Select state…</option>
              {stateOptions.map((state) => (
                <option key={state.code} value={state.code}>
                  {state.code} — {state.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="PIN code">
            <SkeuoInput
              value={form.postalCode}
              onChange={(e) => update("postalCode", e.target.value)}
              maxLength={12}
              className="font-mono"
              placeholder="560103"
            />
          </Field>
          <Field label="LUT number" hint="Export of services under LUT is zero-rated with no IGST.">
            <SkeuoInput
              value={form.lutNumber}
              onChange={(e) => update("lutNumber", e.target.value.toUpperCase())}
              className="font-mono"
              placeholder="AD290523000123X"
            />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Support email">
            <SkeuoInput
              value={form.supportEmail}
              onChange={(e) => update("supportEmail", e.target.value)}
              type="email"
              placeholder="billing@example.com"
            />
          </Field>
          <Field label="Support phone">
            <SkeuoInput
              value={form.supportPhone}
              onChange={(e) => update("supportPhone", e.target.value)}
              className="font-mono"
              placeholder="+91 80 4000 0000"
            />
          </Field>
          <Field label="Invoice prefix" hint="Up to 4 characters, alphanumeric.">
            <SkeuoInput
              value={form.invoicePrefix}
              onChange={(e) => update("invoicePrefix", e.target.value)}
              maxLength={4}
              className="font-mono"
            />
          </Field>
          <Field label="Credit note prefix" hint="Used for GST credit notes on refunds.">
            <SkeuoInput
              value={form.creditNotePrefix}
              onChange={(e) => update("creditNotePrefix", e.target.value)}
              maxLength={4}
              className="font-mono"
            />
          </Field>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-3">
            <label className="flex items-start gap-3 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel p-3 text-xs">
              <input
                type="checkbox"
                checked={form.priceIncludesTax}
                onChange={(e) => update("priceIncludesTax", e.target.checked)}
                className="mt-0.5 h-4 w-4"
                aria-label="Prices include GST"
              />
              <span>
                <span className="block font-semibold text-text">Prices already include GST</span>
                <span className="block text-text-muted">
                  Off (recommended): the tenant pays the recharge amount plus GST, and the wallet is
                  credited the full taxable value. On: GST is carved out of the amount the tenant
                  enters, so the wallet credit is smaller.
                </span>
              </span>
            </label>
            <label className="flex items-start gap-3 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel p-3 text-xs">
              <input
                type="checkbox"
                checked={form.exportZeroRated}
                onChange={(e) => update("exportZeroRated", e.target.checked)}
                className="mt-0.5 h-4 w-4"
                aria-label="Zero-rate exports of services"
              />
              <span>
                <span className="block font-semibold text-text">Zero-rate export of services</span>
                <span className="block text-text-muted">
                  Applies when the buyer is outside India and the place of supply is outside India.
                  Enable only for eligible exports covered by your tax policy. Off charges configured IGST. Payment currency alone does not qualify a supply as an export.
                </span>
              </span>
            </label>
          </div>
          <Field label="Invoice and checkout terms" hint="Shown before payment and printed on invoice PDFs. Use this for your tax policy and customer-facing GST terms.">
            <SkeuoTextarea
              rows={4}
              value={form.invoiceTerms}
              aria-label="Invoice and checkout terms"
              onChange={(e) => update("invoiceTerms", e.target.value)}
              placeholder="Payment received. This is a computer-generated invoice."
            />
          </Field>
        </div>

        <section className="space-y-3 rounded-xl border border-surface-border-subtle p-4" aria-label="GST checkout preview">
          <h3 className="text-sm font-semibold">Preview checkout charges</h3>
          <p className="text-xs text-text-muted">Uses this draft’s rules. Preview does not save settings or create a payment.</p>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Preview amount"><SkeuoInput type="number" min="0.01" value={previewAmount} onChange={(event) => { setPreviewAmount(event.target.value); setPreview(null); }} /></Field>
            <Field label="Payment currency"><select className="mt-2 w-full rounded-lg border p-2" value={previewCurrency} onChange={(event) => { setPreviewCurrency(event.target.value); setPreview(null); }}><option>INR</option><option>USD</option></select></Field>
            <Field label="Customer location"><select className="mt-2 w-full rounded-lg border p-2" value={previewBuyer} onChange={(event) => { setPreviewBuyer(event.target.value); setPreview(null); }}><option value="same">Same Indian state</option><option value="different">Different Indian state</option><option value="export">Eligible export customer</option></select></Field>
          </div>
          <SkeuoButton type="button" disabled={previewBusy} onClick={() => void previewCheckout()}>{previewBusy ? "Calculating…" : "Preview checkout"}</SkeuoButton>
          {preview && <dl data-testid="admin-gst-preview" className="grid gap-3 text-sm sm:grid-cols-4">{[["Taxable value", `${preview.currency} ${preview.subtotal.toFixed(2)}`], ["GST", `${preview.currency} ${preview.tax.toFixed(2)} · ${preview.taxKind}`], ["Total payable", `${preview.currency} ${preview.total.toFixed(2)}`], ["Wallet credit", `INR ${preview.creditInr.toFixed(2)}`]].map(([label, value]) => <div key={label}><dt className="text-xs text-text-muted">{label}</dt><dd className="mt-1 font-semibold">{value}</dd></div>)}</dl>}
        </section>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-surface-border-subtle pt-4">
          <p className="max-w-xl text-[11px] text-text-subtle">
            Supplier identity is snapshotted onto each invoice at payment time, so an update here
            never rewrites a document already issued to a tenant.
          </p>
          <div className="flex items-center gap-3">
            {error ? <span className="text-xs font-medium text-status-error">{error}</span> : null}
            {!error && savedAt ? (
              <span className="text-xs font-medium text-emerald-700">Saved.</span>
            ) : null}
            <SkeuoButton type="button" disabled={busy || settings.loading} onClick={save}>
              {busy ? "Saving…" : "Save GST settings"}
            </SkeuoButton>
          </div>
        </div>

        {settings.error ? (
          <p className="rounded-skeuo-sm border border-red-200 bg-red-50 p-3 text-xs text-red-700">
            {settings.error}
          </p>
        ) : null}
      </fieldset>
    </DevCard>
  );
}
