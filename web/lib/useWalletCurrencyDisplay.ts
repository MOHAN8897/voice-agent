"use client";

import { useCallback, useEffect, useState } from "react";

export type WalletCurrencyDisplay = "both" | "USD" | "INR";

const STORAGE_KEY = "admin-wallet-currency-display";

export function isWalletCurrencyDisplay(value: string): value is WalletCurrencyDisplay {
  return value === "both" || value === "USD" || value === "INR";
}

export function useWalletCurrencyDisplay() {
  const [display, setDisplay] = useState<WalletCurrencyDisplay>("both");

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved && isWalletCurrencyDisplay(saved)) setDisplay(saved);
    } catch {
      // Keep the default when browser storage is unavailable.
    }
  }, []);

  const updateDisplay = useCallback((value: WalletCurrencyDisplay) => {
    setDisplay(value);
    try {
      window.localStorage.setItem(STORAGE_KEY, value);
    } catch {
      // Apply the preference for this page even if it cannot be saved.
    }
  }, []);

  return { display, setDisplay: updateDisplay };
}
