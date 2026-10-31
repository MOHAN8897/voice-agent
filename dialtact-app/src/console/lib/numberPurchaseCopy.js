// What a tenant reads when buying a number does not go as planned.
//
// The server is the source of truth: every buy refusal and every purchase status
// carries a plain-language `message` from server/services/saas/number_purchase_errors.py
// that already says whether the wallet was charged or refunded. These fallbacks
// cover only what the server cannot say: the request never reached it, or the
// console stopped waiting before provisioning finished. They follow the same
// rules: no carrier names, no codes, and always the money state.

export const PURCHASE_COPY = {
  network:
    "We couldn't reach our servers to complete your purchase. Your wallet wasn't charged. Check your connection and try again.",
  unknownRefusal:
    "We couldn't complete your purchase just now. Your wallet wasn't charged. Please try again in a few minutes.",
  stillActivating:
    "Your number is paid for and still being activated. It will appear in your list shortly. Please don't buy it again.",
  needsAttention:
    "Your payment is safe. Activating this number is taking longer than usual and our team has been notified. You don't need to buy it again: we'll finish the setup or refund you.",
  failedRefunded:
    "We couldn't activate this number right now, so we've refunded the charge to your wallet. Please try again later or choose another number.",
  failedRefundPending:
    "We couldn't activate this number. Your refund is being processed and our team has been notified, so you don't need to do anything. Please don't buy this number again.",
  checkingFailed:
    "We couldn't check on your number just now. If you were charged, it will appear in your list or be refunded automatically.",
};

/** Codes after which the chosen number should disappear from the list. */
export const NUMBER_GONE_CODES = new Set(['number_unavailable', 'number_reserved', 'carrier_price_above_retail']);

const looksInternal = (text) => !text || /_[a-z]|HTTP \d|vobiz|telnyx|carrier/i.test(text);

/** Message for a buy request the server refused (an Error from api.js). */
export function buyRefusalMessage(error) {
  if (!error) return PURCHASE_COPY.unknownRefusal;
  if (!error.status) return PURCHASE_COPY.network;
  const message = String(error.message || '');
  return looksInternal(message) ? PURCHASE_COPY.unknownRefusal : message;
}

/** Message for a purchase that was paid but did not end active. */
export function purchaseOutcomeMessage(purchase) {
  if (!purchase) return PURCHASE_COPY.checkingFailed;
  const server = String(purchase.message || purchase.lastError?.message || '');
  if (server && !looksInternal(server)) return server;
  const status = String(purchase.status || '').toLowerCase();
  if (status === 'needs_attention') return PURCHASE_COPY.needsAttention;
  if (status === 'failed') return purchase.refunded ? PURCHASE_COPY.failedRefunded : PURCHASE_COPY.failedRefundPending;
  return PURCHASE_COPY.stillActivating;
}
