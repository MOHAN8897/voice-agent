import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../services/api';

/** Server-published shelf prices plus operator merchandising tags. */
export function usePricingCatalog() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);

  const load = useCallback(async () => {
    const request = ++generation.current;
    setLoading(true);
    setError('');
    try {
      const result = await api.billing.getCatalog();
      if (request === generation.current) setData(result);
    } catch (cause) {
      if (request !== generation.current) return;
      setData(null);
      setError(cause instanceof Error ? cause.message : 'Pricing could not be loaded.');
    } finally {
      if (request === generation.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    return () => { generation.current += 1; };
  }, [load]);

  return { data, error, loading, reload: load };
}

export function pricedTiers(catalog) {
  const tiers = Array.isArray(catalog?.tiers) ? catalog.tiers : [];
  return tiers.filter((tier) => tier?.visible !== false);
}

export function catalogNumberMonthly(catalog) {
  const sku = Array.isArray(catalog?.numberSkus) ? catalog.numberSkus[0] : null;
  const inr = Number(sku?.monthlyInr);
  const usd = Number(sku?.monthlyUsd);
  return {
    inr: Number.isFinite(inr) ? inr : null,
    usd: Number.isFinite(usd) ? usd : null,
  };
}

export function formatInrAmount(value) {
  if (!Number.isFinite(value)) return '—';
  return `₹${value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatUsdAmount(value, digits = 3) {
  if (!Number.isFinite(value)) return '—';
  return `$${value.toFixed(digits)}`;
}
