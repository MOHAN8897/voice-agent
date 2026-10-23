"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { DevCard } from "@/components/dev/DevCard";
import {
  AdminError,
  AdminLoading,
  AdminPageHeader,
  AdminStat,
} from "@/components/admin/AdminNav";
import {
  SkeuoBadge,
  SkeuoButton,
  SkeuoInput,
  SkeuoTable,
  SkeuoTableBody,
  SkeuoTableHead,
  SkeuoTableRow,
  SkeuoTd,
  SkeuoTh,
} from "@/components/ui/skeuo";
import {
  adminAction,
  formatInr,
  formatUsd,
  formatWhen,
  useAdminResource,
} from "@/lib/useAdminResource";
import { portalFetch } from "@/lib/auth-client";
import { isWalletCurrencyDisplay, useWalletCurrencyDisplay } from "@/lib/useWalletCurrencyDisplay";

type Purchase = {
  purchaseId: string;
  tenantId: string;
  e164: string;
  status: string;
  createdAt: string;
};

type WalletRow = {
  tenantId: string;
  name: string;
  status: string;
  balanceInrPaise: number;
  balanceCents: number;
  /** Dollar figure for display; derived server-side when only INR is funded. */
  balanceUsd: number;
  currency: string;
  walletCurrency: string;
  updatedAt: string | null;
};

type Rates = {
  pstnUsdPerMin: number;
  webUsdPerMin: number;
  numberMonthlyUsd: number;
  /** The rate money is actually converted at. */
  fxRateInr: number;
  /** Read-only mirrors at fxRateInr. */
  pstnInrPerMin: number;
  webInrPerMin: number;
  numberMonthlyInr: number;
  pstnLowUsdPerMin?: number | null;
  pstnLowInrPerMin?: number | null;
  pstnMediumUsdPerMin?: number | null;
  pstnMediumInrPerMin?: number | null;
  pstnPremiumUsdPerMin?: number | null;
  pstnPremiumInrPerMin?: number | null;
};

type RateField = "pstn" | "web" | "number" | "pstnLow" | "pstnMedium" | "pstnPremium";
type RateCurrency = "USD" | "INR";

/** Market rate, shown for reference only — charging uses rates.fxRateInr. */
type FxInfo = {
  liveRateInr: number | null;
  source?: string;
  asOf?: string | null;
  chargeRateInr: number;
};

type PaymentSettings = {
  configured: boolean;
  keyId: string;
  testMode: boolean;
  webhookConfigured: boolean;
  internationalEnabled: boolean;
  /** Razorpay has no status endpoint; this is always null by design. */
  internationalVerified: null;
  internationalNote: string;
  currency: string;
  availableCurrencies: string[];
  minCharge: number;
  supportsUpi: boolean;
  settlesIn: string;
};

type PayOrder = {
  orderId: string;
  tenantId: string;
  tenantName: string | null;
  status: string;
  currency: string;
  /** Gross amount charged, in the charge currency. */
  amount: number;
  /** Taxable value in the charge currency. */
  subtotal: number;
  tax: number;
  taxRatePercent: number;
  taxKind: string;
  /** Taxable value settled in INR — what the wallet was credited. */
  amountInr: number;
  /** Gross INR collected (taxable + GST). */
  grossInr: number;
  baseAmountInr: number | null;
  paymentId: string | null;
  paymentMethod: string | null;
  failureCode: string | null;
  failureReason: string | null;
  fee: number | null;
  taxOnFee: number | null;
  settlementId: string | null;
  settledAt: string | null;
  invoiceId: string | null;
  invoiceNumber: string | null;
  invoiceStatus: string | null;
  createdAt: string | null;
  paidAt: string | null;
  expiresAt: string | null;
};

type OrdersResponse = {
  orders: PayOrder[];
  total: number;
  summary: {
    creditedInr: number;
    settledInr: number;
    collectedInr: number;
    byStatus: Record<string, number>;
  };
  limit: number;
  offset: number;
};

type InvoiceRow = {
  invoiceId: string;
  invoiceNumber: string;
  status: string;
  currency: string;
  amount: number;
  gross: number;
  subtotal: number;
  tax: number;
  taxRatePercent: number;
  taxKind: string;
  amountInr: number;
  grossInr: number;
  taxableInr: number;
  taxInr: number;
  cgstInr: number;
  sgstInr: number;
  igstInr: number;
  sacCode: string | null;
  placeOfSupply: string | null;
  customerGstin: string | null;
  fy: string | null;
  sequence: number | null;
  paymentId: string | null;
  orderId: string | null;
  paymentMethod: string | null;
  paidAt: string | null;
  createdAt: string | null;
  tenantName?: string | null;
};

type InvoicesResponse = {
  invoices: InvoiceRow[];
  total: number;
  summary: {
    grossInr: number;
    taxableInr: number;
    taxInr: number;
    cgstInr: number;
    sgstInr: number;
    igstInr: number;
  };
  limit: number;
  offset: number;
};

type RefundRow = {
  refundId: string;
  amount: number;
  currency: string;
  walletReversalInr: number;
  taxReversalInr: number;
  status: string;
  reason: string | null;
  createdBy: string | null;
  createdAt: string | null;
};

type OrderDetail = {
  order: PayOrder;
  invoice: InvoiceRow | null;
  refunds: RefundRow[];
};

type TaxReportRow = {
  taxKind: string;
  count: number;
  taxableInr: number;
  taxInr: number;
  cgstInr: number;
  sgstInr: number;
  igstInr: number;
};

type TaxReport = {
  from: string | null;
  to: string | null;
  issued: TaxReportRow[];
  creditNotes: TaxReportRow;
  net: {
    taxableInr: number;
    taxInr: number;
    cgstInr: number;
    sgstInr: number;
    igstInr: number;
  };
};

const STATUSES = ["", "paid", "failed", "refunded", "pending"] as const;
const TONE: Record<string, "success" | "warning" | "error" | "muted"> = {
  paid: "success",
  active: "success",
  failed: "error",
  refunded: "muted",
  pending: "warning",
};

export default function AdminBillingPage() {
  const [status, setStatus] = useState<string>("");
  const purchases = useAdminResource<{ purchases: Purchase[] }>(
    `/api/dev/admin/purchases${status ? `?status=${status}` : ""}`,
    [status]
  );
  const wallets = useAdminResource<{ wallets: WalletRow[]; currency: string }>(
    "/api/dev/admin/wallets"
  );
  const ratesRes = useAdminResource<{ currency: string; rates: Rates; fx: FxInfo }>(
    "/api/dev/admin/billing-rates"
  );

  const payments = useAdminResource<PaymentSettings>("/api/dev/admin/payments");
  const [intlEnabled, setIntlEnabled] = useState(false);
  const [payCurrency, setPayCurrency] = useState("USD");

  const searchParams = useSearchParams();
  const tenantFromUrl = searchParams.get("tenantId") || "";
  const [tenantId, setTenantId] = useState(tenantFromUrl);
  // Wallet adjustments are kept in USD; price inputs retain their entered currency.
  const [dollars, setDollars] = useState("25");
  const [walletAmountDraft, setWalletAmountDraft] = useState<string | null>(null);
  const [adjustNote, setAdjustNote] = useState("");
  const [pstnUsd, setPstnUsd] = useState("0.09");
  const [webUsd, setWebUsd] = useState("0.07");
  const [numberUsd, setNumberUsd] = useState("4");
  const [pstnInr, setPstnInr] = useState("0");
  const [webInr, setWebInr] = useState("0");
  const [numberInr, setNumberInr] = useState("0");
  const [pstnLowUsd, setPstnLowUsd] = useState("0.05");
  const [pstnMediumUsd, setPstnMediumUsd] = useState("0.09");
  const [pstnPremiumUsd, setPstnPremiumUsd] = useState("0.15");
  const [pstnLowInr, setPstnLowInr] = useState("0");
  const [pstnMediumInr, setPstnMediumInr] = useState("0");
  const [pstnPremiumInr, setPstnPremiumInr] = useState("0");
  const [rateDrafts, setRateDrafts] = useState<
    Partial<Record<RateField, Partial<Record<RateCurrency, string>>>>
  >({});
  const [fxRate, setFxRate] = useState("95.64");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Wallets filter state
  const [query, setQuery] = useState("");
  const [walletStatusFilter, setWalletStatusFilter] = useState("all");
  const [walletBalanceFilter, setWalletBalanceFilter] = useState("all");
  const { display: walletCurrencyDisplay, setDisplay: setWalletCurrencyPreference } = useWalletCurrencyDisplay();

  // Orders filter state
  const [orderQuery, setOrderQuery] = useState("");
  const [orderQueryDraft, setOrderQueryDraft] = useState("");
  const [orderStatus, setOrderStatus] = useState("all");
  const [orderCurrency, setOrderCurrency] = useState("all");
  const [orderFrom, setOrderFrom] = useState("");
  const [orderTo, setOrderTo] = useState("");
  const [orderPage, setOrderPage] = useState(0);
  const [expandedOrder, setExpandedOrder] = useState<string | null>(null);
  const [refundAmount, setRefundAmount] = useState("");
  const [refundReason, setRefundReason] = useState("");
  const [orderDetail, setOrderDetail] = useState<OrderDetail | null>(null);
  const [orderDetailLoading, setOrderDetailLoading] = useState(false);
  const [orderDetailError, setOrderDetailError] = useState<string | null>(null);
  const ORDERS_PAGE_SIZE = 25;

  useEffect(() => {
    // Typing shouldn't refetch every keystroke; the server does the matching.
    const timer = window.setTimeout(() => {
      setOrderQuery(orderQueryDraft.trim());
      setOrderPage(0);
    }, 350);
    return () => window.clearTimeout(timer);
  }, [orderQueryDraft]);

  // Invoices filter state
  const [invoiceQuery, setInvoiceQuery] = useState("");
  const [invoiceQueryDraft, setInvoiceQueryDraft] = useState("");
  const [invoiceStatus, setInvoiceStatus] = useState("all");
  const [invoiceFrom, setInvoiceFrom] = useState("");
  const [invoiceTo, setInvoiceTo] = useState("");
  const [invoicePage, setInvoicePage] = useState(0);
  const INVOICES_PAGE_SIZE = 25;

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setInvoiceQuery(invoiceQueryDraft.trim());
      setInvoicePage(0);
    }, 350);
    return () => window.clearTimeout(timer);
  }, [invoiceQueryDraft]);

  // GST report period (IST calendar days, resolved server-side)
  const [reportFrom, setReportFrom] = useState("");
  const [reportTo, setReportTo] = useState("");

  const orderParams = useMemo(() => {
    const params = new URLSearchParams();
    params.set("limit", String(ORDERS_PAGE_SIZE));
    params.set("offset", String(orderPage * ORDERS_PAGE_SIZE));
    if (orderStatus !== "all") params.set("status", orderStatus);
    if (orderQuery) params.set("q", orderQuery);
    if (orderFrom) params.set("dateFrom", orderFrom);
    if (orderTo) params.set("dateTo", orderTo);
    if (tenantId) params.set("tenantId", tenantId);
    return params.toString();
  }, [orderPage, orderStatus, orderQuery, orderFrom, orderTo, tenantId]);

  const payOrders = useAdminResource<OrdersResponse>(
    `/api/dev/admin/payments/orders?${orderParams}`,
    [orderParams]
  );

  const invoiceParams = useMemo(() => {
    const params = new URLSearchParams();
    params.set("limit", String(INVOICES_PAGE_SIZE));
    params.set("offset", String(invoicePage * INVOICES_PAGE_SIZE));
    if (invoiceStatus !== "all") params.set("status", invoiceStatus);
    if (invoiceQuery) params.set("q", invoiceQuery);
    if (invoiceFrom) params.set("dateFrom", invoiceFrom);
    if (invoiceTo) params.set("dateTo", invoiceTo);
    if (tenantId) params.set("tenantId", tenantId);
    return params.toString();
  }, [invoicePage, invoiceStatus, invoiceQuery, invoiceFrom, invoiceTo, tenantId]);

  const invoices = useAdminResource<InvoicesResponse>(
    `/api/dev/admin/payments/invoices?${invoiceParams}`,
    [invoiceParams]
  );

  const reportParams = useMemo(() => {
    const params = new URLSearchParams();
    if (reportFrom) params.set("dateFrom", reportFrom);
    if (reportTo) params.set("dateTo", reportTo);
    const query = params.toString();
    return query ? `?${query}` : "";
  }, [reportFrom, reportTo]);

  const taxReport = useAdminResource<TaxReport>(
    `/api/dev/admin/payments/tax-report${reportParams}`,
    [reportParams]
  );

  // Purchases filter state
  const [purchaseQuery, setPurchaseQuery] = useState("");

  useEffect(() => {
    if (tenantFromUrl) setTenantId(tenantFromUrl);
  }, [tenantFromUrl]);

  useEffect(() => {
    const r = ratesRes.data?.rates;
    if (!r) return;
    setPstnUsd(String(r.pstnUsdPerMin ?? 0.09));
    setWebUsd(String(r.webUsdPerMin ?? 0.07));
    setNumberUsd(String(r.numberMonthlyUsd ?? 4));
    setPstnInr(String(r.pstnInrPerMin ?? 0));
    setWebInr(String(r.webInrPerMin ?? 0));
    setNumberInr(String(r.numberMonthlyInr ?? 0));
    setPstnLowUsd(String(r.pstnLowUsdPerMin ?? 0.05));
    setPstnMediumUsd(String(r.pstnMediumUsdPerMin ?? 0.09));
    setPstnPremiumUsd(String(r.pstnPremiumUsdPerMin ?? 0.15));
    setPstnLowInr(String(r.pstnLowInrPerMin ?? 0));
    setPstnMediumInr(String(r.pstnMediumInrPerMin ?? 0));
    setPstnPremiumInr(String(r.pstnPremiumInrPerMin ?? 0));
    setFxRate(String(r.fxRateInr ?? 95.64));
  }, [ratesRes.data]);

  const chargeFx = Number(ratesRes.data?.rates?.fxRateInr) || 95.64;
  const liveFx = Number(ratesRes.data?.fx?.liveRateInr) || 0;
  const priceInputCurrency: RateCurrency = walletCurrencyDisplay === "INR" ? "INR" : "USD";
  const proposedFx = Number(fxRate);
  const priceInputFx = Number.isFinite(proposedFx) && proposedFx > 0 ? proposedFx : chargeFx;

  function usdPriceInput(usdAmount: string, fx: number) {
    if (usdAmount.trim() === "") return "";
    const amount = Number(usdAmount);
    if (!Number.isFinite(amount)) return usdAmount;
    return walletCurrencyDisplay === "INR" ? (amount * fx).toFixed(2) : usdAmount;
  }

  function rateInputValue(field: RateField, currency: RateCurrency = priceInputCurrency) {
    const draft = rateDrafts[field];
    const direct = draft?.[currency];
    if (direct !== undefined) return direct;

    const otherCurrency: RateCurrency = currency === "INR" ? "USD" : "INR";
    const otherDraft = draft?.[otherCurrency];
    if (otherDraft !== undefined) {
      if (otherDraft.trim() === "") return "";
      const amount = Number(otherDraft);
      if (!Number.isFinite(amount)) return otherDraft;
      return currency === "INR"
        ? (amount * priceInputFx).toFixed(2)
        : (amount / priceInputFx).toFixed(6).replace(/\.?0+$/, "");
    }

    const currentValues =
      currency === "INR"
        ? { pstn: pstnInr, web: webInr, number: numberInr, pstnLow: pstnLowInr, pstnMedium: pstnMediumInr, pstnPremium: pstnPremiumInr }
        : { pstn: pstnUsd, web: webUsd, number: numberUsd, pstnLow: pstnLowUsd, pstnMedium: pstnMediumUsd, pstnPremium: pstnPremiumUsd };
    return currentValues[field];
  }

  function updateRateInput(field: RateField, value: string) {
    setRateDrafts((current) => ({
      ...current,
      [field]: { ...current[field], [priceInputCurrency]: value },
    }));
  }

  function rateForSave(field: RateField) {
    return rateInputValue(field);
  }

  function updateWalletAmount(value: string) {
    setWalletAmountDraft(value);
    const amount = Number(value);
    if (value.trim() === "") {
      setDollars("");
    } else if (Number.isFinite(amount)) {
      setDollars(String(walletCurrencyDisplay === "INR" ? amount / chargeFx : amount));
    }
  }

  function changeWalletCurrency(value: string) {
    if (!isWalletCurrencyDisplay(value)) return;
    setWalletAmountDraft(null);
    setWalletCurrencyPreference(value);
  }

  function displayedRate(usdValue: number | string, inrValue: number | string) {
    const usdAmount = Number(usdValue);
    const inrAmount = Number(inrValue);
    if (!Number.isFinite(usdAmount) || !Number.isFinite(inrAmount)) return "—";
    const usd = "$" + usdAmount.toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
    const inr = "₹" + inrAmount.toFixed(2);
    if (walletCurrencyDisplay === "USD") return usd;
    if (walletCurrencyDisplay === "INR") return inr;
    return (
      <span className="block leading-5">
        <span className="block">{usd}</span>
        <span className="block text-[11px] font-normal text-text-muted">≈ {inr}</span>
      </span>
    );
  }

  function paymentOrderAmount(order: PayOrder, settlement: boolean) {
    const creditedPaise = Math.round(Number(order.amountInr || 0) * 100);
    const grossInr = Number(order.grossInr || order.amountInr || 0);
    const grossPaise = Math.round(grossInr * 100);
    const usdCents = Math.round((grossInr / chargeFx) * 100);
    const actualCharge = `${order.currency} ${Number(order.amount || 0).toFixed(2)}`;

    if (settlement) {
      return (
        <span className="flex flex-col">
          <span>{formatInr(creditedPaise)}</span>
          <span className="text-[10px] font-normal text-text-muted">wallet credit</span>
        </span>
      );
    }

    if (walletCurrencyDisplay === "INR") {
      return (
        <span className="flex flex-col">
          <span>{formatInr(grossPaise)}</span>
          <span className="text-[10px] font-normal text-text-muted">Charged {actualCharge}</span>
        </span>
      );
    }
    if (walletCurrencyDisplay === "USD") {
      return (
        <span className="flex flex-col">
          <span>{formatUsd(usdCents)}</span>
          <span className="text-[10px] font-normal text-text-muted">Charged {actualCharge}</span>
        </span>
      );
    }
    return (
      <span className="flex flex-col">
        <span>{actualCharge}</span>
        <span className="text-[10px] font-normal text-text-muted">≈ {formatInr(grossPaise)} gross</span>
      </span>
    );
  }

  useEffect(() => {
    const p = payments.data;
    if (!p) return;
    setIntlEnabled(Boolean(p.internationalEnabled));
    setPayCurrency(p.currency || "USD");
  }, [payments.data]);

  function savePayments() {
    return run("payments", async () => {
      await adminAction("/api/dev/admin/payments", {
        method: "PUT",
        body: { internationalEnabled: intlEnabled, currency: payCurrency },
      });
      await Promise.all([payments.reload(), payOrders.reload()]);
    });
  }

  const allWallets = wallets.data?.wallets ?? [];
  const zeroBalanceLabel = walletCurrencyDisplay === "INR" ? "₹0" : walletCurrencyDisplay === "both" ? "$0 / ₹0" : "$0";
  const lowBalanceLabel = walletCurrencyDisplay === "INR"
    ? `₹${(5 * chargeFx).toFixed(2)}`
    : walletCurrencyDisplay === "both"
    ? `$5 / ₹${(5 * chargeFx).toFixed(2)}`
    : "$5";
  const rows = useMemo(() => {
    return allWallets.filter((w) => {
      if (walletStatusFilter !== "all" && (w.status || "").toLowerCase() !== walletStatusFilter.toLowerCase()) return false;
      const bal = w.balanceUsd || 0;
      if (walletBalanceFilter === "funded" && bal <= 0) return false;
      if (walletBalanceFilter === "low" && (bal <= 0 || bal >= 5)) return false;
      if (walletBalanceFilter === "depleted" && bal > 0) return false;
      if (!query.trim()) return true;
      return `${w.name} ${w.tenantId}`.toLowerCase().includes(query.trim().toLowerCase());
    });
  }, [allWallets, walletStatusFilter, walletBalanceFilter, query, walletCurrencyDisplay, chargeFx]);

  const allOrders = payOrders.data?.orders ?? [];
  const orderTotal = payOrders.data?.total ?? 0;
  const orderSummary = payOrders.data?.summary;
  // Status/search/date are matched by the server; currency has no server filter.
  const filteredOrders = useMemo(() => {
    return allOrders.filter((o) => {
      if (orderCurrency !== "all" && (o.currency || "").toUpperCase() !== orderCurrency.toUpperCase()) return false;
      return true;
    });
  }, [allOrders, orderCurrency]);

  const allInvoices = invoices.data?.invoices ?? [];
  const invoiceTotal = invoices.data?.total ?? 0;

  const allPurchases = purchases.data?.purchases ?? [];
  const purchaseRows = useMemo(() => {
    return allPurchases.filter((p) => {
      if (!purchaseQuery.trim()) return true;
      const q = purchaseQuery.trim().toLowerCase();
      return `${p.e164} ${p.tenantId} ${p.purchaseId}`.toLowerCase().includes(q);
    });
  }, [allPurchases, purchaseQuery]);

  const failed = purchaseRows.filter((p) => p.status === "failed").length;
  function walletUsdCents(wallet: WalletRow) {
    const cents = Math.round(wallet.balanceCents || 0);
    const paise = Math.round(wallet.balanceInrPaise || 0);
    return Math.round(cents + paise / chargeFx);
  }

  function walletInrPaise(wallet: WalletRow) {
    const cents = Math.round(wallet.balanceCents || 0);
    const paise = Math.round(wallet.balanceInrPaise || 0);
    return Math.round(paise + cents * chargeFx);
  }

  function walletBalanceLabel(wallet: WalletRow) {
    const usd = formatUsd(walletUsdCents(wallet));
    const inr = formatInr(walletInrPaise(wallet));
    if (walletCurrencyDisplay === "USD") return usd;
    if (walletCurrencyDisplay === "INR") return inr;
    return `${usd} / ${inr}`;
  }

  function renderWalletBalance(wallet: WalletRow) {
    const usd = formatUsd(walletUsdCents(wallet));
    const inr = formatInr(walletInrPaise(wallet));

    if (walletCurrencyDisplay === "USD") return usd;
    if (walletCurrencyDisplay === "INR") return inr;
    return (
      <span className="block leading-5">
        <span className="block">{usd}</span>
        <span className="block text-[11px] font-normal text-text-muted">≈ {inr}</span>
      </span>
    );
  }

  const totalUsdCents = rows.reduce(
    (sum, w) => sum + walletUsdCents(w),
    0
  );
  const totalInrPaise = rows.reduce((sum, w) => sum + walletInrPaise(w), 0);

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy("");
    }
  }

  function adjust(sign: 1 | -1) {
    const fallbackAmount = walletCurrencyDisplay === "INR" ? Number(dollars) * chargeFx : Number(dollars);
    const amount = Math.abs(walletAmountDraft === null ? fallbackAmount : Number(walletAmountDraft));
    const note = adjustNote.trim();
    if (!tenantId || !Number.isFinite(amount) || amount <= 0) {
      setError(`Pick a tenant and enter a positive ${priceInputCurrency} amount.`);
      return;
    }
    if (note.length < 8) {
      setError("Write an admin statement (8+ characters) before adjusting a wallet.");
      return;
    }
    return run(sign > 0 ? "credit" : "debit", async () => {
      await adminAction("/api/dev/admin/wallets/adjust", {
        method: "POST",
        body: {
          tenantId,
          ...(walletCurrencyDisplay === "INR"
            ? { amountInrPaise: Math.round(amount * 100) * sign }
            : { amountUsdCents: Math.round(amount * 100) * sign }),
          reason: sign > 0 ? "admin_grant" : "admin_debit",
          note,
        },
      });
      setAdjustNote("");
      setWalletAmountDraft(null);
      await wallets.reload();
    });
  }

  function saveRates() {
    const pstnRate = rateForSave("pstn");
    const webRate = rateForSave("web");
    const numberRate = rateForSave("number");
    const pstnLowRate = rateForSave("pstnLow");
    const pstnMediumRate = rateForSave("pstnMedium");
    const pstnPremiumRate = rateForSave("pstnPremium");
    const enteredRates = [
      Number(pstnRate),
      Number(webRate),
      Number(numberRate),
      Number(pstnLowRate),
      Number(pstnMediumRate),
      Number(pstnPremiumRate),
    ];
    const nextRates = {
      rateCurrency: priceInputCurrency,
      pstnUsdPerMin: priceInputCurrency === "USD" && rateDrafts.pstn ? pstnRate : undefined,
      webUsdPerMin: priceInputCurrency === "USD" && rateDrafts.web ? webRate : undefined,
      numberMonthlyUsd: priceInputCurrency === "USD" && rateDrafts.number ? numberRate : undefined,
      pstnInrPerMin: priceInputCurrency === "INR" && rateDrafts.pstn ? pstnRate : undefined,
      webInrPerMin: priceInputCurrency === "INR" && rateDrafts.web ? webRate : undefined,
      didMonthlyInr: priceInputCurrency === "INR" && rateDrafts.number ? numberRate : undefined,
      pstnLowUsdPerMin: priceInputCurrency === "USD" && rateDrafts.pstnLow ? pstnLowRate : undefined,
      pstnMediumUsdPerMin: priceInputCurrency === "USD" && rateDrafts.pstnMedium ? pstnMediumRate : undefined,
      pstnPremiumUsdPerMin: priceInputCurrency === "USD" && rateDrafts.pstnPremium ? pstnPremiumRate : undefined,
      pstnLowInrPerMin: priceInputCurrency === "INR" && rateDrafts.pstnLow ? pstnLowRate : undefined,
      pstnMediumInrPerMin: priceInputCurrency === "INR" && rateDrafts.pstnMedium ? pstnMediumRate : undefined,
      pstnPremiumInrPerMin: priceInputCurrency === "INR" && rateDrafts.pstnPremium ? pstnPremiumRate : undefined,
      fxRateInr: Number(fxRate),
    };
    if (
      [pstnRate, webRate, numberRate, pstnLowRate, pstnMediumRate, pstnPremiumRate].some((value) => value.trim() === "") ||
      enteredRates.some((value, index) => !Number.isFinite(value) || (index !== 2 ? value <= 0 : value < 0)) ||
      !Number.isFinite(nextRates.fxRateInr) || nextRates.fxRateInr <= 0
    ) {
      setError("Enter valid positive prices and a positive INR per USD charge rate.");
      return;
    }
    return run("rates", async () => {
      await adminAction("/api/dev/admin/billing-rates", {
        method: "PUT",
        body: nextRates,
      });
      await ratesRes.reload();
      setRateDrafts({});
    });
  }

  function retry(id: string) {
    return run(`retry:${id}`, async () => {
      await adminAction(`/api/dev/admin/purchases/${id}/retry-provision`);
      await purchases.reload();
    });
  }

  function refund(id: string) {
    if (!window.confirm("Refund this purchase? Money is returned to the original payment method.")) {
      return;
    }
    return run(`refund:${id}`, async () => {
      await adminAction(`/api/dev/admin/purchases/${id}/refund`);
      await purchases.reload();
    });
  }

  async function downloadFile(path: string, fallbackName: string) {
    const res = await portalFetch("dev", path);
    if (!res.ok) {
      let message = `${res.status} ${res.statusText}`;
      try {
        const body = await res.json();
        message = body?.detail?.error?.message ?? body?.detail ?? body?.error?.message ?? message;
      } catch {
        /* non-JSON error body */
      }
      throw new Error(message);
    }
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = /filename="?([^";]+)"?/i.exec(disposition);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = match?.[1] || fallbackName;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  async function loadOrderDetail(orderId: string) {
    setOrderDetailLoading(true);
    setOrderDetailError(null);
    try {
      const detail = await adminAction<OrderDetail>(
        `/api/dev/admin/payments/orders/${encodeURIComponent(orderId)}`,
        { method: "GET" }
      );
      setOrderDetail(detail);
    } catch (e) {
      setOrderDetail(null);
      setOrderDetailError(e instanceof Error ? e.message : "Could not load this order.");
    } finally {
      setOrderDetailLoading(false);
    }
  }

  function toggleOrder(orderId: string) {
    if (expandedOrder === orderId) {
      setExpandedOrder(null);
      setOrderDetail(null);
      setOrderDetailError(null);
      return;
    }
    setExpandedOrder(orderId);
    setOrderDetail(null);
    setRefundAmount("");
    setRefundReason("");
    void loadOrderDetail(orderId);
  }

  function reconcileOrder(orderId: string) {
    return run(`reconcile:${orderId}`, async () => {
      await adminAction(`/api/dev/admin/payments/orders/${encodeURIComponent(orderId)}/reconcile`, {
        method: "POST",
      });
      await Promise.all([
        loadOrderDetail(orderId),
        payOrders.reload(),
        invoices.reload(),
        taxReport.reload(),
      ]);
    });
  }

  function refundOrder(order: PayOrder) {
    const reason = refundReason.trim();
    if (reason.length < 8) {
      setError("Write a refund reason (8+ characters) — it is stored on the credit note.");
      return;
    }
    const amount = refundAmount.trim() === "" ? null : Number(refundAmount);
    if (amount !== null && (!Number.isFinite(amount) || amount <= 0)) {
      setError("Refund amount must be positive, or left blank for the full charge.");
      return;
    }
    const amountLabel = amount === null ? "the full remaining charge" : `${order.currency} ${amount.toFixed(2)}`;
    if (
      !window.confirm(
        `Refund ${amountLabel} for ${order.orderId}?\n\nThe wallet is debited the taxable value and a GST credit note is issued immediately.`
      )
    ) {
      return;
    }
    return run(`orderRefund:${order.orderId}`, async () => {
      await adminAction(`/api/dev/admin/payments/orders/${encodeURIComponent(order.orderId)}/refund`, {
        method: "POST",
        body: { ...(amount === null ? {} : { amount }), reason },
      });
      setRefundAmount("");
      setRefundReason("");
      await Promise.all([
        loadOrderDetail(order.orderId),
        payOrders.reload(),
        invoices.reload(),
        taxReport.reload(),
      ]);
    });
  }

  function clearOrderFilters() {
    setOrderQueryDraft("");
    setOrderQuery("");
    setOrderStatus("all");
    setOrderCurrency("all");
    setOrderFrom("");
    setOrderTo("");
    setOrderPage(0);
  }

  function clearInvoiceFilters() {
    setInvoiceQueryDraft("");
    setInvoiceQuery("");
    setInvoiceStatus("all");
    setInvoiceFrom("");
    setInvoiceTo("");
    setInvoicePage(0);
  }

  return (
    <div className="space-y-6 p-6" data-testid="admin-billing-wallets-page">
      <AdminPageHeader
        title="Wallet & rates"
        description={`Wallets and prices display in ${walletCurrencyDisplay === "both" ? "USD and INR" : walletCurrencyDisplay}. Rates preserve their entered currency precision, including exact INR paise.`}
        actions={
          <div className="flex flex-wrap items-end gap-3">
            <label className="block text-xs">
              <span className="mb-1 block text-text-muted">Display currency</span>
              <select
                value={walletCurrencyDisplay}
                onChange={(e) => changeWalletCurrency(e.currentTarget.value)}
                className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
                aria-label="Billing display currency"
                data-testid="admin-wallet-currency-display"
              >
                <option value="both">USD and INR</option>
                <option value="USD">USD</option>
                <option value="INR">INR</option>
              </select>
            </label>
            {tenantId ? (
              <Link href={`/dev/admin/tenants/${tenantId}?tab=wallet`}>
                <SkeuoButton variant="ghost">Tenant wallet cockpit</SkeuoButton>
              </Link>
            ) : null}
          </div>
        }
      />

      <AdminError error={error} />
      <AdminError error={purchases.error} />
      <AdminError error={wallets.error} />
      <AdminError error={ratesRes.error} />
      <AdminError error={payOrders.error} />
      <AdminError error={invoices.error} />
      <AdminError error={taxReport.error} />
      <AdminError error={orderDetailError} />

      <div className="grid gap-4 sm:grid-cols-4">
        <AdminStat
          label={`Wallet total${walletCurrencyDisplay === "both" ? " (USD / INR)" : ` (${walletCurrencyDisplay})`}`}
          value={
            walletCurrencyDisplay === "USD" ? formatUsd(totalUsdCents) :
            walletCurrencyDisplay === "INR" ? formatInr(totalInrPaise) : (
              <>
                <span className="block">{formatUsd(totalUsdCents)}</span>
                <span className="block text-sm text-text-muted">≈ {formatInr(totalInrPaise)}</span>
              </>
            )
          }
          hint={walletCurrencyDisplay === "both" ? `INR equivalent at ₹${chargeFx.toFixed(2)} per USD` : undefined}
        />
        <AdminStat
          label={`PSTN ${walletCurrencyDisplay === "INR" ? "₹" : "$"}/min`}
          value={displayedRate(ratesRes.data?.rates?.pstnUsdPerMin ?? Number.NaN, ratesRes.data?.rates?.pstnInrPerMin ?? Number.NaN)}
        />
        <AdminStat
          label={`Number rental ${walletCurrencyDisplay === "INR" ? "₹" : "$"}/mo`}
          value={displayedRate(ratesRes.data?.rates?.numberMonthlyUsd ?? Number.NaN, ratesRes.data?.rates?.numberMonthlyInr ?? Number.NaN)}
        />
        <AdminStat label="Failed purchases" value={failed} tone={failed > 0 ? "warn" : "good"} />
      </div>

      <DevCard title="USD → INR reference">
        <div className="flex flex-wrap items-end gap-4">
          <div className="text-xs">
            <span className="mb-1 block text-text-muted">Charge rate (USD → INR)</span>
            <SkeuoInput
              value={fxRate}
              onChange={(e) => setFxRate(e.target.value)}
              inputMode="decimal"
              className="w-28"
              aria-label="Charge FX rate INR per USD"
              data-testid="admin-fx-charge-rate"
            />
            <span className="mt-1 block text-[11px] text-text-muted">
              Used for currency equivalents; directly entered INR rates keep their paise value.
            </span>
          </div>
          <div
            className="text-xs"
            data-testid="admin-fx-live"
            aria-label={`Live rate ${liveFx || "unavailable"} rupees per dollar`}
          >
            <span className="mb-1 block text-text-muted">Live market rate</span>
            <p className="font-mono text-lg font-semibold">
              {liveFx ? `₹${liveFx.toFixed(2)}` : "unavailable"}
            </p>
            <span className="block text-[11px] text-text-muted">
              {ratesRes.data?.fx?.asOf ? `as of ${ratesRes.data.fx.asOf}` : "reference only"}
              {ratesRes.data?.fx?.source ? ` · ${ratesRes.data.fx.source}` : ""}
            </span>
          </div>
        </div>
      </DevCard>

      <DevCard title={`Platform & Channel Prices (${walletCurrencyDisplay === "both" ? "USD + INR" : walletCurrencyDisplay})`}>
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 py-2">
          <div>
            <h4 className="text-sm font-semibold text-text">Platform &amp; Channel Calling Prices Centralized</h4>
            <p className="mt-1 text-xs text-text-muted max-w-2xl">
              All PSTN Voice Call Pricing (Economical, Standard, and Gemini 3.8 Live Premium tiers), Web Agent calling rates,
              and Phone Number DID rental pricing have been consolidated into the unified <strong>Stacks &amp; Tiers</strong> management workbench.
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Link
              href="/dev/stack"
              className="inline-flex items-center gap-2 rounded-xl bg-accent-primary px-4 py-2.5 text-xs font-semibold text-white shadow-sm hover:opacity-95 transition-opacity"
            >
              <span>⚙️ Manage Prices in Stacks &amp; Tiers</span>
            </Link>
            <Link
              href="/dev/stack#gst-billing"
              className="inline-flex items-center gap-2 rounded-xl border border-surface-border-subtle bg-surface-panel-raised px-4 py-2.5 text-xs font-semibold text-text shadow-sm hover:opacity-95 transition-opacity"
            >
              <span>GST &amp; invoice identity</span>
            </Link>
          </div>
        </div>
        <div className="mt-3 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-3 text-[11px] text-text-muted">
          GST is applied on top of these shelf prices unless “prices include tax” is enabled in{" "}
          <Link href="/dev/stack#gst-billing" className="font-semibold text-accent-primary hover:underline">
            GST &amp; invoicing
          </Link>
          . A recharge credits the wallet only the taxable value; the GST collected is a statutory
          liability, not tenant credit.
        </div>
      </DevCard>

      <DevCard title={`Manual wallet top-up / debit (${walletCurrencyDisplay === "both" ? "USD" : walletCurrencyDisplay})`}>
        <p className="mb-3 text-xs text-text-muted">
          Credits or debits one wallet leg (USD or INR, matching the tenant&apos;s primary currency).
          Every change requires a statement for the audit trail.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Tenant</span>
            <select
              className="min-w-[220px] rounded-skeuo-sm border border-border bg-surface-panel px-3 py-2 text-sm"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
              aria-label="Tenant for wallet adjust"
            >
              <option value="">Select tenant…</option>
              {(wallets.data?.wallets ?? []).map((w) => (
                <option key={w.tenantId} value={w.tenantId}>
                    {w.name} — {walletBalanceLabel(w)}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Amount ({priceInputCurrency})</span>
            <SkeuoInput
              value={walletAmountDraft ?? usdPriceInput(dollars, chargeFx)}
              onChange={(e) => updateWalletAmount(e.target.value)}
              inputMode="decimal"
              aria-label={`${priceInputCurrency} amount`}
              className="w-28"
              data-testid="admin-wallet-usd-amount"
            />
            {walletCurrencyDisplay === "both" && (
              <span className="mt-1 block font-mono text-[11px] text-text-muted">
                ≈ ₹{((Number(dollars) || 0) * chargeFx).toFixed(2)}
              </span>
            )}
          </label>
          <label className="block min-w-[240px] flex-1 text-xs">
            <span className="mb-1 block text-text-muted">Admin statement</span>
            <SkeuoInput
              value={adjustNote}
              onChange={(e) => setAdjustNote(e.target.value)}
              placeholder="Required — why is this adjustment being made?"
              data-testid="admin-wallet-note"
            />
          </label>
          <SkeuoButton type="button" disabled={!!busy} onClick={() => void adjust(1)}>
            {busy === "credit" ? "Crediting…" : "Increase"}
          </SkeuoButton>
          <SkeuoButton
            type="button"
            variant="secondary"
            disabled={!!busy}
            onClick={() => void adjust(-1)}
          >
            {busy === "debit" ? "Debiting…" : "Decrease"}
          </SkeuoButton>
        </div>
      </DevCard>

      <DevCard title="Payments — Razorpay">
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span
            className={`rounded-skeuo-sm px-2 py-1 font-semibold ${
              payments.data?.configured ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
            }`}
            data-testid="admin-payments-status"
          >
            {payments.data?.configured ? "Keys configured" : "Keys missing"}
            {payments.data?.testMode ? " · test mode" : " · live"}
          </span>
          {payments.data?.keyId ? (
            <span className="font-mono text-text-muted">{payments.data.keyId}</span>
          ) : null}
          <span
            className={`rounded-skeuo-sm px-2 py-1 font-semibold ${
              payments.data?.webhookConfigured
                ? "bg-emerald-50 text-emerald-700"
                : "bg-amber-50 text-amber-800"
            }`}
            data-testid="admin-payments-webhook-status"
            title="Razorpay webhooks are the authoritative payment state. Without the secret, confirmation depends on the browser callback."
          >
            {payments.data?.webhookConfigured ? "Webhook verified" : "Webhook secret missing"}
          </span>
          <span className="text-text-muted">Settles in {payments.data?.settlesIn ?? "INR"}</span>
          <span
            className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-2 py-1 font-medium text-text-subtle"
            data-testid="admin-payments-intl-badge"
          >
            International: Not checkable via API
          </span>
        </div>

        <div className="mt-4 flex flex-wrap items-end gap-4">
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={intlEnabled}
              onChange={(e) => setIntlEnabled(e.target.checked)}
              aria-label="Enable international payments"
              data-testid="admin-payments-international"
              className="h-4 w-4"
            />
            <span>
              Accept international cards
              <span className="block text-[11px] text-text-muted">
                Cards issued outside India. Settles to INR.
              </span>
            </span>
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Charge currency</span>
            <select
              value={payCurrency}
              onChange={(e) => setPayCurrency(e.target.value)}
              aria-label="Charge currency"
              data-testid="admin-payments-currency"
              disabled={!intlEnabled}
              className="rounded-skeuo-sm border border-border bg-surface-panel px-3 py-2 text-sm disabled:opacity-50"
            >
              {(payments.data?.availableCurrencies ?? ["INR"]).map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <SkeuoButton
            type="button"
            disabled={!!busy || !payments.data?.configured}
            onClick={() => void savePayments()}
          >
            {busy === "payments" ? "Saving…" : "Save payment settings"}
          </SkeuoButton>
        </div>

        {intlEnabled && (
          <p className="mt-3 text-[11px] text-amber-800" data-testid="admin-payments-hint">
            Razorpay provides no API to confirm this, so it has to be checked by hand:{' '}
            <strong>Account &amp; Settings → Payment methods → International payments</strong>. Until
            Razorpay approves it, foreign cards are declined at checkout.
          </p>
        )}
        {intlEnabled && payCurrency !== "INR" && (
          <p className="mt-2 text-[11px] text-text-muted">
            UPI and netbanking are hidden automatically for {payCurrency} orders — they settle
            domestically only. Minimum charge {payments.data?.minCharge} {payCurrency}.
          </p>
        )}
      </DevCard>

      <DevCard
        title="Payment orders"
        description="Every recharge attempt with cart value, GST and wallet credit shown separately, so a mismatch can be traced without opening the provider dashboard."
        actions={
          <span className="text-[11px] text-text-muted">
            {payOrders.loading ? "Loading…" : `${orderTotal} order${orderTotal === 1 ? "" : "s"}`}
          </span>
        }
      >
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          <div className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-3">
            <span className="block text-[11px] text-text-muted">Collected (gross INR)</span>
            <span className="mt-1 block font-mono text-lg font-semibold">
              {formatInr(Math.round((orderSummary?.collectedInr ?? 0) * 100))}
            </span>
            <span className="block text-[11px] text-text-subtle">tenant payments, including GST</span>
          </div>
          <div className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-3">
            <span className="block text-[11px] text-text-muted">Credited to wallets</span>
            <span className="mt-1 block font-mono text-lg font-semibold">
              {formatInr(Math.round((orderSummary?.creditedInr ?? 0) * 100))}
            </span>
            <span className="block text-[11px] text-text-subtle">taxable value — GST is not spendable credit</span>
          </div>
          <div className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-3">
            <span className="block text-[11px] text-text-muted">GST collected</span>
            <span className="mt-1 block font-mono text-lg font-semibold">
              {formatInr(
                Math.round(
                  Math.max(0, (orderSummary?.collectedInr ?? 0) - (orderSummary?.creditedInr ?? 0)) * 100
                )
              )}
            </span>
            <span className="block text-[11px] text-text-subtle">a statutory liability, not platform revenue</span>
          </div>
        </div>

        <div className="mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Search orders</label>
              <SkeuoInput
                placeholder="Tenant, order or payment ID…"
                value={orderQueryDraft}
                onChange={(e) => setOrderQueryDraft(e.target.value)}
                aria-label="Search orders"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Status</label>
              <select
                value={orderStatus}
                onChange={(e) => {
                  setOrderStatus(e.target.value);
                  setOrderPage(0);
                }}
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
              >
                <option value="all">All statuses</option>
                <option value="created">Created</option>
                <option value="attempted">Attempted</option>
                <option value="paid">Paid</option>
                <option value="failed">Failed</option>
                <option value="partially_refunded">Partially refunded</option>
                <option value="refunded">Refunded</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Currency</label>
              <select
                value={orderCurrency}
                onChange={(e) => setOrderCurrency(e.target.value)}
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
              >
                <option value="all">All currencies</option>
                <option value="INR">INR</option>
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
                <option value="GBP">GBP</option>
                <option value="AED">AED</option>
              </select>
              <span className="mt-1 block text-[10px] text-text-subtle">filters this page only</span>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">From (IST)</label>
              <SkeuoInput
                type="date"
                value={orderFrom}
                onChange={(e) => {
                  setOrderFrom(e.target.value);
                  setOrderPage(0);
                }}
                aria-label="Orders from date"
                className="mt-1"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">To (IST)</label>
              <SkeuoInput
                type="date"
                value={orderTo}
                onChange={(e) => {
                  setOrderTo(e.target.value);
                  setOrderPage(0);
                }}
                aria-label="Orders to date"
                className="mt-1"
              />
            </div>
          </div>
          <div className="flex items-center justify-between border-t border-surface-border-subtle pt-2 text-xs text-text-muted">
            <span>
              Showing <strong className="text-text">{filteredOrders.length}</strong> of{" "}
              <strong className="text-text">{orderTotal}</strong> matching orders
            </span>
            {(orderQuery || orderStatus !== "all" || orderCurrency !== "all" || orderFrom || orderTo) && (
              <button type="button" onClick={clearOrderFilters} className="text-accent-primary hover:underline">
                Clear filters
              </button>
            )}
          </div>
        </div>

        <AdminLoading loading={payOrders.loading} />
        <p className="mb-2 text-[11px] text-text-muted">
          Tax is the GST collected on the charge. Wallet credit is the taxable value the tenant can
          spend; refunds reverse both in the same proportion.
        </p>
        <SkeuoTable>
          <SkeuoTableHead>
            <SkeuoTh>Tenant / order</SkeuoTh>
            <SkeuoTh>{walletCurrencyDisplay === "both" ? "Charged" : `Charged (${walletCurrencyDisplay} equiv.)`}</SkeuoTh>
            <SkeuoTh>GST</SkeuoTh>
            <SkeuoTh>Wallet credit</SkeuoTh>
            <SkeuoTh>Status</SkeuoTh>
            <SkeuoTh>Invoice</SkeuoTh>
            <SkeuoTh>When</SkeuoTh>
            <SkeuoTh className="text-right">Detail</SkeuoTh>
          </SkeuoTableHead>
          <SkeuoTableBody>
            {filteredOrders.map((o) => {
              const open = expandedOrder === o.orderId;
              return (
                <Fragment key={o.orderId}>
                  <SkeuoTableRow>
                    <SkeuoTd>
                      <div className="font-medium text-text">{o.tenantName || "Unassigned"}</div>
                      <div className="font-mono text-[10px] text-text-muted">{o.orderId}</div>
                    </SkeuoTd>
                    <SkeuoTd className="font-mono font-medium">{paymentOrderAmount(o, false)}</SkeuoTd>
                    <SkeuoTd className="font-mono text-xs">
                      {o.currency} {Number(o.tax || 0).toFixed(2)}
                      <span className="block text-[10px] text-text-muted">
                        {o.taxRatePercent ? `${o.taxRatePercent}% · ${o.taxKind}` : "no GST"}
                      </span>
                    </SkeuoTd>
                    <SkeuoTd className="font-mono">{paymentOrderAmount(o, true)}</SkeuoTd>
                    <SkeuoTd>
                      <SkeuoBadge
                        tone={
                          o.status === "paid"
                            ? "success"
                            : o.status === "failed"
                            ? "error"
                            : o.status === "refunded"
                            ? "muted"
                            : "warning"
                        }
                      >
                        {o.status}
                      </SkeuoBadge>
                      {o.failureCode ? (
                        <span className="mt-1 block text-[10px] text-status-error">{o.failureCode}</span>
                      ) : null}
                    </SkeuoTd>
                    <SkeuoTd className="text-xs">
                      {o.invoiceId ? (
                        <button
                          type="button"
                          className="font-mono text-accent-primary hover:underline"
                          onClick={() =>
                            void run(`invoicePdf:${o.invoiceId}`, () =>
                              downloadFile(
                                `/api/dev/admin/payments/invoices/${o.invoiceId}/pdf`,
                                `${o.invoiceNumber || "invoice"}.pdf`
                              )
                            )
                          }
                        >
                          {o.invoiceNumber}
                        </button>
                      ) : (
                        <span className="text-text-muted">—</span>
                      )}
                    </SkeuoTd>
                    <SkeuoTd className="text-xs text-text-muted">{formatWhen(o.createdAt)}</SkeuoTd>
                    <SkeuoTd className="text-right">
                      <SkeuoButton type="button" size="sm" variant="secondary" onClick={() => toggleOrder(o.orderId)}>
                        {open ? "Close" : "Open"}
                      </SkeuoButton>
                    </SkeuoTd>
                  </SkeuoTableRow>
                  {open ? (
                    <SkeuoTableRow>
                      <SkeuoTd colSpan={8} className="bg-surface-panel-inset/60">
                        <AdminLoading loading={orderDetailLoading} />
                        {!orderDetailLoading && orderDetail && orderDetail.order.orderId === o.orderId ? (
                          <div className="space-y-4 py-1">
                            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                              <div>
                                <span className="block text-[10px] uppercase tracking-wide text-text-subtle">Listed value</span>
                                <span className="font-mono text-sm">
                                  {o.currency} {Number(orderDetail.order.subtotal || 0).toFixed(2)}
                                </span>
                              </div>
                              <div>
                                <span className="block text-[10px] uppercase tracking-wide text-text-subtle">GST</span>
                                <span className="font-mono text-sm">
                                  {o.currency} {Number(orderDetail.order.tax || 0).toFixed(2)}
                                </span>
                              </div>
                              <div>
                                <span className="block text-[10px] uppercase tracking-wide text-text-subtle">Charged</span>
                                <span className="font-mono text-sm">
                                  {o.currency} {Number(orderDetail.order.amount || 0).toFixed(2)}
                                </span>
                              </div>
                              <div>
                                <span className="block text-[10px] uppercase tracking-wide text-text-subtle">Credited wallet</span>
                                <span className="font-mono text-sm">
                                  {formatInr(Math.round(Number(orderDetail.order.amountInr || 0) * 100))}
                                </span>
                              </div>
                              <div>
                                <span className="block text-[10px] uppercase tracking-wide text-text-subtle">Payment ID</span>
                                <span className="font-mono text-xs break-all">{orderDetail.order.paymentId || "—"}</span>
                              </div>
                              <div>
                                <span className="block text-[10px] uppercase tracking-wide text-text-subtle">Method</span>
                                <span className="text-xs capitalize">{orderDetail.order.paymentMethod || "—"}</span>
                              </div>
                              <div>
                                <span className="block text-[10px] uppercase tracking-wide text-text-subtle">Provider fee / tax</span>
                                <span className="font-mono text-xs">
                                  {orderDetail.order.fee === null
                                    ? "—"
                                    : `${o.currency} ${Number(orderDetail.order.fee).toFixed(2)} + ${Number(
                                        orderDetail.order.taxOnFee || 0
                                      ).toFixed(2)}`}
                                </span>
                              </div>
                              <div>
                                <span className="block text-[10px] uppercase tracking-wide text-text-subtle">Settlement</span>
                                <span className="font-mono text-xs break-all">
                                  {orderDetail.order.settlementId || "—"}
                                  {orderDetail.order.settledAt ? ` · ${formatWhen(orderDetail.order.settledAt)}` : ""}
                                </span>
                              </div>
                            </div>

                            {orderDetail.order.failureReason || orderDetail.order.failureCode ? (
                              <p className="rounded-skeuo-sm border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                                <strong>{orderDetail.order.failureCode || "Payment failed"}:</strong>{" "}
                                {orderDetail.order.failureReason || "No provider reason recorded."}
                              </p>
                            ) : null}

                            <div className="grid gap-4 lg:grid-cols-2">
                              <div className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel p-3">
                                <div className="flex items-center justify-between gap-3">
                                  <span className="text-xs font-semibold text-text">GST invoice</span>
                                  {orderDetail.invoice ? (
                                    <SkeuoButton
                                      type="button"
                                      size="sm"
                                      variant="secondary"
                                      onClick={() =>
                                        void run(`invoicePdf:${orderDetail.invoice?.invoiceId}`, () =>
                                          downloadFile(
                                            `/api/dev/admin/payments/invoices/${orderDetail.invoice?.invoiceId}/pdf`,
                                            `${orderDetail.invoice?.invoiceNumber || "invoice"}.pdf`
                                          )
                                        )
                                      }
                                    >
                                      Download PDF
                                    </SkeuoButton>
                                  ) : null}
                                </div>
                                {orderDetail.invoice ? (
                                  <div className="mt-2 space-y-1 text-xs">
                                    <p className="font-mono font-medium">{orderDetail.invoice.invoiceNumber}</p>
                                    <p className="text-text-muted">
                                      Taxable {formatInr(Math.round(orderDetail.invoice.taxableInr * 100))} · GST{" "}
                                      {formatInr(Math.round(orderDetail.invoice.taxInr * 100))} · Gross{" "}
                                      {formatInr(Math.round(orderDetail.invoice.grossInr * 100))}
                                    </p>
                                    <p className="text-text-muted">
                                      {orderDetail.invoice.taxKind === "cgst_sgst"
                                        ? `CGST ${formatInr(Math.round(orderDetail.invoice.cgstInr * 100))} + SGST ${formatInr(
                                            Math.round(orderDetail.invoice.sgstInr * 100)
                                          )}`
                                        : orderDetail.invoice.taxKind === "igst"
                                        ? `IGST ${formatInr(Math.round(orderDetail.invoice.igstInr * 100))}`
                                        : "No GST (export of services or tax disabled)"}
                                    </p>
                                    <p className="text-text-muted">
                                      Place of supply: {orderDetail.invoice.placeOfSupply || "—"}
                                      {orderDetail.invoice.customerGstin
                                        ? ` · Buyer GSTIN ${orderDetail.invoice.customerGstin}`
                                        : ""}
                                    </p>
                                    <p className="text-text-muted">Status: {orderDetail.invoice.status}</p>
                                  </div>
                                ) : (
                                  <p className="mt-2 text-xs text-text-muted">
                                    No invoice yet — one is issued automatically when the provider reports the
                                    payment captured.
                                  </p>
                                )}
                              </div>

                              <div className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel p-3">
                                <span className="text-xs font-semibold text-text">Refunds</span>
                                {orderDetail.refunds.length === 0 ? (
                                  <p className="mt-2 text-xs text-text-muted">No refunds on this order.</p>
                                ) : (
                                  <ul className="mt-2 space-y-2 text-xs">
                                    {orderDetail.refunds.map((r) => (
                                      <li key={r.refundId} className="rounded border border-surface-border-subtle p-2">
                                        <div className="flex items-center justify-between gap-2">
                                          <span className="font-mono text-[11px]">{r.refundId}</span>
                                          <SkeuoBadge tone={r.status === "processed" ? "success" : r.status === "failed" ? "error" : "warning"}>
                                            {r.status}
                                          </SkeuoBadge>
                                        </div>
                                        <p className="mt-1 text-text-muted">
                                          {r.currency} {Number(r.amount || 0).toFixed(2)} · wallet −
                                          {formatInr(Math.round(Number(r.walletReversalInr || 0) * 100))} · GST credit{" "}
                                          {formatInr(Math.round(Number(r.taxReversalInr || 0) * 100))}
                                        </p>
                                        {r.reason ? <p className="text-text-subtle">{r.reason}</p> : null}
                                      </li>
                                    ))}
                                  </ul>
                                )}
                              </div>
                            </div>

                            <div className="flex flex-wrap items-end gap-3 border-t border-surface-border-subtle pt-3">
                              {orderDetail.order.status !== "paid" &&
                              orderDetail.order.status !== "partially_refunded" &&
                              orderDetail.order.status !== "refunded" ? (
                                <>
                                  <SkeuoButton
                                    type="button"
                                    size="sm"
                                    disabled={busy === `reconcile:${o.orderId}`}
                                    onClick={() => void reconcileOrder(o.orderId)}
                                  >
                                    {busy === `reconcile:${o.orderId}` ? "Checking…" : "Reconcile with provider"}
                                  </SkeuoButton>
                                  <span className="text-[11px] text-text-muted">
                                    Asks Razorpay for the real payment state and settles this order locally.
                                  </span>
                                </>
                              ) : null}
                              {orderDetail.order.status === "paid" ||
                              orderDetail.order.status === "partially_refunded" ? (
                                <>
                                  <label className="block text-xs">
                                    <span className="mb-1 block text-text-muted">Refund amount ({o.currency})</span>
                                    <SkeuoInput
                                      value={refundAmount}
                                      onChange={(e) => setRefundAmount(e.target.value)}
                                      inputMode="decimal"
                                      placeholder="Full remaining"
                                      className="w-32"
                                      aria-label="Refund amount"
                                    />
                                  </label>
                                  <label className="block min-w-[240px] flex-1 text-xs">
                                    <span className="mb-1 block text-text-muted">Reason (stored on the credit note)</span>
                                    <SkeuoInput
                                      value={refundReason}
                                      onChange={(e) => setRefundReason(e.target.value)}
                                      placeholder="8+ characters — why is this being refunded?"
                                      aria-label="Refund reason"
                                    />
                                  </label>
                                  <SkeuoButton
                                    type="button"
                                    size="sm"
                                    variant="secondary"
                                    disabled={busy === `orderRefund:${o.orderId}`}
                                    onClick={() => void refundOrder(orderDetail.order)}
                                  >
                                    {busy === `orderRefund:${o.orderId}` ? "Refunding…" : "Refund & issue credit note"}
                                  </SkeuoButton>
                                </>
                              ) : null}
                            </div>
                          </div>
                        ) : null}
                      </SkeuoTd>
                    </SkeuoTableRow>
                  ) : null}
                </Fragment>
              );
            })}
            {filteredOrders.length === 0 && !payOrders.loading && (
              <SkeuoTableRow>
                <SkeuoTd className="text-center py-6 text-text-muted" colSpan={8}>
                  No payment orders found matching current filters.
                </SkeuoTd>
              </SkeuoTableRow>
            )}
          </SkeuoTableBody>
        </SkeuoTable>
        <div className="mt-3 flex items-center justify-between text-xs text-text-muted">
          <span>
            {orderTotal === 0
              ? "No orders"
              : `${orderPage * ORDERS_PAGE_SIZE + 1}–${Math.min(
                  orderPage * ORDERS_PAGE_SIZE + allOrders.length,
                  orderTotal
                )} of ${orderTotal}`}
          </span>
          <div className="flex gap-2">
            <SkeuoButton
              type="button"
              size="sm"
              variant="secondary"
              disabled={orderPage === 0 || payOrders.loading}
              onClick={() => setOrderPage((p) => Math.max(0, p - 1))}
            >
              Previous
            </SkeuoButton>
            <SkeuoButton
              type="button"
              size="sm"
              variant="secondary"
              disabled={
                payOrders.loading || (orderPage + 1) * ORDERS_PAGE_SIZE >= orderTotal
              }
              onClick={() => setOrderPage((p) => p + 1)}
            >
              Next
            </SkeuoButton>
          </div>
        </div>
      </DevCard>

      <DevCard
        title="Invoices & credit notes"
        description="GST invoice register. Serial numbers are consecutive per financial year; every invoice stores the supplier and buyer identity used at the time of payment."
        actions={
          <SkeuoButton
            type="button"
            size="sm"
            variant="secondary"
            disabled={!!busy || invoices.loading}
            onClick={() => {
              const params = new URLSearchParams();
              if (invoiceFrom) params.set("dateFrom", invoiceFrom);
              if (invoiceTo) params.set("dateTo", invoiceTo);
              if (tenantId) params.set("tenantId", tenantId);
              const query = params.toString();
              void run("invoiceCsv", () =>
                downloadFile(
                  `/api/dev/admin/payments/invoices/export${query ? `?${query}` : ""}`,
                  "invoices.csv"
                )
              );
            }}
          >
            {busy === "invoiceCsv" ? "Preparing…" : "Export CSV"}
          </SkeuoButton>
        }
      >
        <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-3">
            <span className="block text-[11px] text-text-muted">Gross invoiced</span>
            <span className="mt-1 block font-mono text-lg font-semibold">
              {formatInr(Math.round((invoices.data?.summary.grossInr ?? 0) * 100))}
            </span>
          </div>
          <div className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-3">
            <span className="block text-[11px] text-text-muted">Taxable value</span>
            <span className="mt-1 block font-mono text-lg font-semibold">
              {formatInr(Math.round((invoices.data?.summary.taxableInr ?? 0) * 100))}
            </span>
          </div>
          <div className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-3">
            <span className="block text-[11px] text-text-muted">GST invoiced</span>
            <span className="mt-1 block font-mono text-lg font-semibold">
              {formatInr(Math.round((invoices.data?.summary.taxInr ?? 0) * 100))}
            </span>
            <span className="block text-[11px] text-text-subtle">
              CGST {formatInr(Math.round((invoices.data?.summary.cgstInr ?? 0) * 100))} · SGST{" "}
              {formatInr(Math.round((invoices.data?.summary.sgstInr ?? 0) * 100))} · IGST{" "}
              {formatInr(Math.round((invoices.data?.summary.igstInr ?? 0) * 100))}
            </span>
          </div>
          <div className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-3">
            <span className="block text-[11px] text-text-muted">Invoices</span>
            <span className="mt-1 block font-mono text-lg font-semibold">{invoiceTotal}</span>
            <span className="block text-[11px] text-text-subtle">
              {tenantId ? "filtered to selected tenant" : "all tenants"}
            </span>
          </div>
        </div>

        <div className="mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Search invoices</label>
              <SkeuoInput
                placeholder="Number, payment ID, GSTIN, tenant…"
                value={invoiceQueryDraft}
                onChange={(e) => setInvoiceQueryDraft(e.target.value)}
                aria-label="Search invoices"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Status</label>
              <select
                value={invoiceStatus}
                onChange={(e) => {
                  setInvoiceStatus(e.target.value);
                  setInvoicePage(0);
                }}
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
              >
                <option value="all">All statuses</option>
                <option value="paid">Paid</option>
                <option value="partially_refunded">Partially refunded</option>
                <option value="refunded">Refunded</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">From (IST)</label>
              <SkeuoInput
                type="date"
                value={invoiceFrom}
                onChange={(e) => {
                  setInvoiceFrom(e.target.value);
                  setInvoicePage(0);
                }}
                aria-label="Invoices from date"
                className="mt-1"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">To (IST)</label>
              <SkeuoInput
                type="date"
                value={invoiceTo}
                onChange={(e) => {
                  setInvoiceTo(e.target.value);
                  setInvoicePage(0);
                }}
                aria-label="Invoices to date"
                className="mt-1"
              />
            </div>
          </div>
          <div className="flex items-center justify-between border-t border-surface-border-subtle pt-2 text-xs text-text-muted">
            <span>
              Showing <strong className="text-text">{allInvoices.length}</strong> of{" "}
              <strong className="text-text">{invoiceTotal}</strong> invoices
            </span>
            {(invoiceQuery || invoiceStatus !== "all" || invoiceFrom || invoiceTo) && (
              <button type="button" onClick={clearInvoiceFilters} className="text-accent-primary hover:underline">
                Clear filters
              </button>
            )}
          </div>
        </div>

        <AdminLoading loading={invoices.loading} />
        <SkeuoTable>
          <SkeuoTableHead>
            <SkeuoTh>Invoice</SkeuoTh>
            <SkeuoTh>Tenant</SkeuoTh>
            <SkeuoTh>Taxable</SkeuoTh>
            <SkeuoTh>GST</SkeuoTh>
            <SkeuoTh>Gross</SkeuoTh>
            <SkeuoTh>Status</SkeuoTh>
            <SkeuoTh className="text-right">PDF</SkeuoTh>
          </SkeuoTableHead>
          <SkeuoTableBody>
            {allInvoices.map((inv) => (
              <SkeuoTableRow key={inv.invoiceId}>
                <SkeuoTd>
                  <span className="font-mono text-xs font-medium">{inv.invoiceNumber}</span>
                  <span className="block text-[10px] text-text-muted">
                    {formatWhen(inv.createdAt)}
                    {inv.fy ? ` · FY ${inv.fy}` : ""}
                  </span>
                </SkeuoTd>
                <SkeuoTd className="text-xs">
                  <span className="font-medium text-text">{inv.tenantName || "—"}</span>
                  {inv.customerGstin ? (
                    <span className="block font-mono text-[10px] text-text-muted">{inv.customerGstin}</span>
                  ) : null}
                </SkeuoTd>
                <SkeuoTd className="font-mono text-xs">
                  {formatInr(Math.round(Number(inv.taxableInr || 0) * 100))}
                </SkeuoTd>
                <SkeuoTd className="font-mono text-xs">
                  {formatInr(Math.round(Number(inv.taxInr || 0) * 100))}
                  <span className="block text-[10px] text-text-muted">
                    {inv.taxKind === "cgst_sgst"
                      ? `C ${formatInr(Math.round(inv.cgstInr * 100))} / S ${formatInr(Math.round(inv.sgstInr * 100))}`
                      : inv.taxKind === "igst"
                      ? `IGST ${formatInr(Math.round(inv.igstInr * 100))}`
                      : inv.taxKind}
                  </span>
                </SkeuoTd>
                <SkeuoTd className="font-mono text-xs font-medium">
                  {formatInr(Math.round(Number(inv.grossInr || 0) * 100))}
                </SkeuoTd>
                <SkeuoTd>
                  <SkeuoBadge
                    tone={
                      inv.status === "paid"
                        ? "success"
                        : inv.status === "refunded"
                        ? "muted"
                        : "warning"
                    }
                  >
                    {inv.status}
                  </SkeuoBadge>
                  <span className="mt-1 block text-[10px] text-text-muted">
                    {inv.placeOfSupply || "—"}
                  </span>
                </SkeuoTd>
                <SkeuoTd className="text-right">
                  <SkeuoButton
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={busy === `adminInvoicePdf:${inv.invoiceId}`}
                    onClick={() =>
                      void run(`adminInvoicePdf:${inv.invoiceId}`, () =>
                        downloadFile(
                          `/api/dev/admin/payments/invoices/${inv.invoiceId}/pdf`,
                          `${inv.invoiceNumber}.pdf`
                        )
                      )
                    }
                  >
                    {busy === `adminInvoicePdf:${inv.invoiceId}` ? "…" : "PDF"}
                  </SkeuoButton>
                </SkeuoTd>
              </SkeuoTableRow>
            ))}
            {allInvoices.length === 0 && !invoices.loading && (
              <SkeuoTableRow>
                <SkeuoTd className="text-center py-6 text-text-muted" colSpan={7}>
                  No invoices match the current filters. Invoices are created automatically when a
                  recharge payment is captured.
                </SkeuoTd>
              </SkeuoTableRow>
            )}
          </SkeuoTableBody>
        </SkeuoTable>
        <div className="mt-3 flex items-center justify-between text-xs text-text-muted">
          <span>
            {invoiceTotal === 0
              ? "No invoices"
              : `${invoicePage * INVOICES_PAGE_SIZE + 1}–${Math.min(
                  invoicePage * INVOICES_PAGE_SIZE + allInvoices.length,
                  invoiceTotal
                )} of ${invoiceTotal}`}
          </span>
          <div className="flex gap-2">
            <SkeuoButton
              type="button"
              size="sm"
              variant="secondary"
              disabled={invoicePage === 0 || invoices.loading}
              onClick={() => setInvoicePage((p) => Math.max(0, p - 1))}
            >
              Previous
            </SkeuoButton>
            <SkeuoButton
              type="button"
              size="sm"
              variant="secondary"
              disabled={
                invoices.loading || (invoicePage + 1) * INVOICES_PAGE_SIZE >= invoiceTotal
              }
              onClick={() => setInvoicePage((p) => p + 1)}
            >
              Next
            </SkeuoButton>
          </div>
        </div>
      </DevCard>

      <DevCard
        title="GST tax report"
        description="Net GST position for a filing period: invoices issued minus credit notes raised. Dates are Indian calendar days (IST)."
        actions={
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-[11px] text-text-muted">
              <span className="mb-1 block">From</span>
              <SkeuoInput
                type="date"
                value={reportFrom}
                onChange={(e) => setReportFrom(e.target.value)}
                aria-label="Tax report from date"
                className="mt-0 w-36"
              />
            </label>
            <label className="text-[11px] text-text-muted">
              <span className="mb-1 block">To</span>
              <SkeuoInput
                type="date"
                value={reportTo}
                onChange={(e) => setReportTo(e.target.value)}
                aria-label="Tax report to date"
                className="mt-0 w-36"
              />
            </label>
          </div>
        }
      >
        <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <div className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-3">
            <span className="block text-[11px] text-text-muted">Net taxable</span>
            <span className="mt-1 block font-mono text-lg font-semibold">
              {formatInr(Math.round((taxReport.data?.net.taxableInr ?? 0) * 100))}
            </span>
          </div>
          <div className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-3">
            <span className="block text-[11px] text-text-muted">Net CGST</span>
            <span className="mt-1 block font-mono text-lg font-semibold">
              {formatInr(Math.round((taxReport.data?.net.cgstInr ?? 0) * 100))}
            </span>
          </div>
          <div className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-3">
            <span className="block text-[11px] text-text-muted">Net SGST</span>
            <span className="mt-1 block font-mono text-lg font-semibold">
              {formatInr(Math.round((taxReport.data?.net.sgstInr ?? 0) * 100))}
            </span>
          </div>
          <div className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-3">
            <span className="block text-[11px] text-text-muted">Net IGST</span>
            <span className="mt-1 block font-mono text-lg font-semibold">
              {formatInr(Math.round((taxReport.data?.net.igstInr ?? 0) * 100))}
            </span>
          </div>
          <div className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-3">
            <span className="block text-[11px] text-text-muted">Net GST payable</span>
            <span className="mt-1 block font-mono text-lg font-semibold">
              {formatInr(Math.round((taxReport.data?.net.taxInr ?? 0) * 100))}
            </span>
          </div>
        </div>

        <AdminLoading loading={taxReport.loading} />
        <SkeuoTable>
          <SkeuoTableHead>
            <SkeuoTh>Supply type</SkeuoTh>
            <SkeuoTh>Documents</SkeuoTh>
            <SkeuoTh>Taxable</SkeuoTh>
            <SkeuoTh>CGST</SkeuoTh>
            <SkeuoTh>SGST</SkeuoTh>
            <SkeuoTh>IGST</SkeuoTh>
            <SkeuoTh>Total GST</SkeuoTh>
          </SkeuoTableHead>
          <SkeuoTableBody>
            {(taxReport.data?.issued ?? []).map((row) => (
              <SkeuoTableRow key={row.taxKind}>
                <SkeuoTd className="text-xs font-medium capitalize">
                  {row.taxKind === "cgst_sgst"
                    ? "Intra-state (CGST + SGST)"
                    : row.taxKind === "igst"
                    ? "Inter-state (IGST)"
                    : row.taxKind === "export"
                    ? "Export of services"
                    : row.taxKind}
                </SkeuoTd>
                <SkeuoTd className="font-mono text-xs">{row.count}</SkeuoTd>
                <SkeuoTd className="font-mono text-xs">{formatInr(Math.round(row.taxableInr * 100))}</SkeuoTd>
                <SkeuoTd className="font-mono text-xs">{formatInr(Math.round(row.cgstInr * 100))}</SkeuoTd>
                <SkeuoTd className="font-mono text-xs">{formatInr(Math.round(row.sgstInr * 100))}</SkeuoTd>
                <SkeuoTd className="font-mono text-xs">{formatInr(Math.round(row.igstInr * 100))}</SkeuoTd>
                <SkeuoTd className="font-mono text-xs font-medium">{formatInr(Math.round(row.taxInr * 100))}</SkeuoTd>
              </SkeuoTableRow>
            ))}
            {taxReport.data?.creditNotes ? (
              <SkeuoTableRow>
                <SkeuoTd className="text-xs font-medium text-red-700">Less: credit notes</SkeuoTd>
                <SkeuoTd className="font-mono text-xs">{taxReport.data.creditNotes.count}</SkeuoTd>
                <SkeuoTd className="font-mono text-xs">
                  −{formatInr(Math.round(taxReport.data.creditNotes.taxableInr * 100))}
                </SkeuoTd>
                <SkeuoTd className="font-mono text-xs">
                  −{formatInr(Math.round(taxReport.data.creditNotes.cgstInr * 100))}
                </SkeuoTd>
                <SkeuoTd className="font-mono text-xs">
                  −{formatInr(Math.round(taxReport.data.creditNotes.sgstInr * 100))}
                </SkeuoTd>
                <SkeuoTd className="font-mono text-xs">
                  −{formatInr(Math.round(taxReport.data.creditNotes.igstInr * 100))}
                </SkeuoTd>
                <SkeuoTd className="font-mono text-xs font-medium text-red-700">
                  −{formatInr(Math.round(taxReport.data.creditNotes.taxInr * 100))}
                </SkeuoTd>
              </SkeuoTableRow>
            ) : null}
            <SkeuoTableRow>
              <SkeuoTd className="text-xs font-semibold">Net for the period</SkeuoTd>
              <SkeuoTd>—</SkeuoTd>
              <SkeuoTd className="font-mono text-xs font-semibold">
                {formatInr(Math.round((taxReport.data?.net.taxableInr ?? 0) * 100))}
              </SkeuoTd>
              <SkeuoTd className="font-mono text-xs font-semibold">
                {formatInr(Math.round((taxReport.data?.net.cgstInr ?? 0) * 100))}
              </SkeuoTd>
              <SkeuoTd className="font-mono text-xs font-semibold">
                {formatInr(Math.round((taxReport.data?.net.sgstInr ?? 0) * 100))}
              </SkeuoTd>
              <SkeuoTd className="font-mono text-xs font-semibold">
                {formatInr(Math.round((taxReport.data?.net.igstInr ?? 0) * 100))}
              </SkeuoTd>
              <SkeuoTd className="font-mono text-xs font-bold">
                {formatInr(Math.round((taxReport.data?.net.taxInr ?? 0) * 100))}
              </SkeuoTd>
            </SkeuoTableRow>
            {(taxReport.data?.issued ?? []).length === 0 && !taxReport.loading && (
              <SkeuoTableRow>
                <SkeuoTd className="text-center py-6 text-text-muted" colSpan={7}>
                  No invoices or credit notes in this period.
                </SkeuoTd>
              </SkeuoTableRow>
            )}
          </SkeuoTableBody>
        </SkeuoTable>
        <p className="mt-3 text-[11px] text-text-subtle">
          The export CSV above includes the per-invoice CGST/SGST/IGST split your GSTR-1 filing
          needs. Credit notes reduce the liability in the period they were issued, not the original
          invoice period.
        </p>
      </DevCard>

      <DevCard title="Tenant wallets">
        <div className="mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Search wallet</label>
              <SkeuoInput
                placeholder="Search tenant name or id…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search wallets"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Balance level</label>
              <select
                value={walletBalanceFilter}
                onChange={(e) => setWalletBalanceFilter(e.target.value)}
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
              >
                <option value="all">All balances</option>
                <option value="funded">Funded (&gt; {zeroBalanceLabel})</option>
                <option value="low">Low balance (&lt; {lowBalanceLabel})</option>
                <option value="depleted">Zero / Depleted ({zeroBalanceLabel})</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Workspace status</label>
              <select
                value={walletStatusFilter}
                onChange={(e) => setWalletStatusFilter(e.target.value)}
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
              >
                <option value="all">All statuses</option>
                <option value="active">Active</option>
                <option value="suspended">Suspended</option>
                <option value="past_due">Past Due</option>
                <option value="deleted">Deleted</option>
              </select>
            </div>
          </div>
          <div className="flex items-center justify-between border-t border-surface-border-subtle pt-2 text-xs text-text-muted">
            <span>
              Showing <strong className="text-text">{rows.length}</strong> of{" "}
              <strong className="text-text">{allWallets.length}</strong> workspaces
            </span>
            {(query.trim() || walletBalanceFilter !== "all" || walletStatusFilter !== "all") && (
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  setWalletBalanceFilter("all");
                  setWalletStatusFilter("all");
                }}
                className="text-accent-primary hover:underline"
              >
                Clear filters
              </button>
            )}
          </div>
        </div>

        <AdminLoading loading={wallets.loading} />
        <SkeuoTable>
          <SkeuoTableHead>
            <SkeuoTh>Tenant</SkeuoTh>
            <SkeuoTh>Status</SkeuoTh>
            <SkeuoTh>
              {walletCurrencyDisplay === "both" ? "Balance (USD / INR)" : `Balance (${walletCurrencyDisplay})`}
            </SkeuoTh>
            <SkeuoTh>Updated</SkeuoTh>
            <SkeuoTh className="text-right">Select</SkeuoTh>
          </SkeuoTableHead>
          <SkeuoTableBody>
            {rows.map((w) => (
              <SkeuoTableRow key={w.tenantId}>
                <SkeuoTd>
                  <Link href={`/dev/admin/tenants/${w.tenantId}?tab=wallet`} className="font-medium text-accent-primary hover:underline">
                    {w.name}
                  </Link>
                  <p className="font-mono text-[10px] text-text-subtle">{w.tenantId}</p>
                </SkeuoTd>
                <SkeuoTd>
                  <SkeuoBadge tone={w.status === "active" ? "success" : w.status === "deleted" ? "error" : "warning"}>
                    {w.status || "active"}
                  </SkeuoBadge>
                </SkeuoTd>
                <SkeuoTd className="font-mono font-medium" data-testid="admin-wallet-balance-cell">
                  {renderWalletBalance(w)}
                </SkeuoTd>
                <SkeuoTd className="text-xs text-text-muted">{formatWhen(w.updatedAt)}</SkeuoTd>
                <SkeuoTd className="text-right">
                  <SkeuoButton type="button" size="sm" onClick={() => setTenantId(w.tenantId)}>
                    Use
                  </SkeuoButton>
                </SkeuoTd>
              </SkeuoTableRow>
            ))}
            {rows.length === 0 && !wallets.loading && (
              <SkeuoTableRow>
                <SkeuoTd className="text-center py-6 text-text-muted" colSpan={5}>
                  No workspaces found matching current filters.
                </SkeuoTd>
              </SkeuoTableRow>
            )}
          </SkeuoTableBody>
        </SkeuoTable>
      </DevCard>

      <DevCard title="Number purchases">
        <div className="mb-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-1">
              {STATUSES.map((s) => (
                <button
                  key={s || "all"}
                  type="button"
                  onClick={() => setStatus(s)}
                  className={`rounded-skeuo-sm px-3 py-1 text-xs font-medium transition-colors ${
                    status === s
                      ? "bg-accent-primary text-white"
                      : "bg-surface-panel-raised text-text-muted hover:text-text"
                  }`}
                >
                  {s || "all"}
                </button>
              ))}
            </div>

            <div className="min-w-[220px]">
              <SkeuoInput
                placeholder="Search number, tenant, ID…"
                value={purchaseQuery}
                onChange={(e) => setPurchaseQuery(e.target.value)}
                aria-label="Search purchases"
              />
            </div>
          </div>

          <div className="flex items-center justify-between border-t border-surface-border-subtle pt-2 text-xs text-text-muted">
            <span>
              Showing <strong className="text-text">{purchaseRows.length}</strong> of{" "}
              <strong className="text-text">{allPurchases.length}</strong> purchases
            </span>
            {(status || purchaseQuery.trim()) && (
              <button
                type="button"
                onClick={() => {
                  setStatus("");
                  setPurchaseQuery("");
                }}
                className="text-accent-primary hover:underline"
              >
                Clear filters
              </button>
            )}
          </div>
        </div>

        <AdminLoading loading={purchases.loading} />
        <SkeuoTable>
          <SkeuoTableHead>
            <SkeuoTh>Number</SkeuoTh>
            <SkeuoTh>Tenant</SkeuoTh>
            <SkeuoTh>Status</SkeuoTh>
            <SkeuoTh>When</SkeuoTh>
            <SkeuoTh className="text-right">Actions</SkeuoTh>
          </SkeuoTableHead>
          <SkeuoTableBody>
            {purchaseRows.map((p) => (
              <SkeuoTableRow key={p.purchaseId}>
                <SkeuoTd className="font-mono font-medium">{p.e164}</SkeuoTd>
                <SkeuoTd className="font-mono text-xs text-text-muted">{p.tenantId}</SkeuoTd>
                <SkeuoTd>
                  <SkeuoBadge tone={TONE[p.status] || "muted"}>{p.status}</SkeuoBadge>
                </SkeuoTd>
                <SkeuoTd className="text-xs text-text-muted">{formatWhen(p.createdAt)}</SkeuoTd>
                <SkeuoTd className="space-x-2 text-right">
                  {p.status === "failed" && (
                    <SkeuoButton
                      type="button"
                      size="sm"
                      disabled={busy === `retry:${p.purchaseId}`}
                      onClick={() => void retry(p.purchaseId)}
                    >
                      Retry
                    </SkeuoButton>
                  )}
                  {(p.status === "paid" || p.status === "failed") && (
                    <SkeuoButton
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={busy === `refund:${p.purchaseId}`}
                      onClick={() => void refund(p.purchaseId)}
                    >
                      Refund
                    </SkeuoButton>
                  )}
                </SkeuoTd>
              </SkeuoTableRow>
            ))}
            {purchaseRows.length === 0 && !purchases.loading && (
              <SkeuoTableRow>
                <SkeuoTd className="text-center py-6 text-text-muted" colSpan={5}>
                  No number purchases found matching current filters.
                </SkeuoTd>
              </SkeuoTableRow>
            )}
          </SkeuoTableBody>
        </SkeuoTable>
      </DevCard>
    </div>
  );
}
