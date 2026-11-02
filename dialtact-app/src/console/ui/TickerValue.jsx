import React, { useRef } from 'react';
import { useReducedMotion } from 'framer-motion';
import { NumberTicker } from '@/components/ui/number-ticker';

// "₹1,24,500.50", "42", "3.5%", "12 min": a number with an optional prefix and suffix.
const NUMBER = /^(\D*?)(-?\d[\d,]*(?:\.\d+)?)(.*)$/;

/**
 * TickerValue — a metric's number counts up once when it first comes into view (Magic UI
 * Number Ticker), keeping the value's own prefix, suffix, decimals and digit grouping
 * (Indian grouping for rupees). Only the first number counts up: a later refresh shows
 * the new value straight away. Anything that is not a single number, and everything
 * under reduced motion, renders as is (DESIGN.md → Motion).
 */
export function TickerValue({ value }) {
  const reduce = useReducedMotion();
  const first = useRef(null);
  if (reduce || (typeof value !== 'string' && typeof value !== 'number')) return value;
  const match = String(value).match(NUMBER);
  if (!match || /\d/.test(match[3])) return value;
  const [, prefix, digits, suffix] = match;
  const target = Number(digits.replace(/,/g, ''));
  if (!Number.isFinite(target)) return value;
  if (first.current === null) first.current = String(value);
  if (first.current !== String(value)) return value;
  const decimals = digits.includes('.') ? digits.split('.')[1].length : 0;
  // Indian grouping when the value already uses it (1,24,500) or is in rupees.
  const locale = prefix.includes('\u20b9') || /\d,\d{2},\d{3}/.test(digits) ? 'en-IN' : 'en-US';
  return (
    <>
      {prefix}
      <NumberTicker value={target} decimalPlaces={decimals} locale={locale} />
      {suffix}
    </>
  );
}
