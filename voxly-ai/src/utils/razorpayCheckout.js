export function loadRazorpayScript() {
  return new Promise((resolve, reject) => {
    if (typeof window !== 'undefined' && window.Razorpay) {
      resolve(window.Razorpay);
      return;
    }
    const existing = document.querySelector('script[data-razorpay-checkout]');
    if (existing) {
      existing.addEventListener('load', () => resolve(window.Razorpay));
      existing.addEventListener('error', reject);
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.async = true;
    script.dataset.razorpayCheckout = '1';
    script.onload = () => resolve(window.Razorpay);
    script.onerror = reject;
    document.body.appendChild(script);
  });
}

export async function openRazorpayWalletCheckout({
  order,
  keyId,
  user,
  onSuccess,
  onError,
  hideUpi = true,
}) {
  const Razorpay = await loadRazorpayScript();
  // `amountMinor` is the order amount in the order's own currency subunit.
  // Razorpay validates checkout against the order, so these two must match it
  // exactly or the payment is rejected after the customer has entered details.
  const currency = order.currency || 'INR';
  const options = {
    key: order.keyId || keyId,
    amount: order.amountMinor,
    currency,
    name: 'Voxly AI',
    description: 'Wallet top-up',
    order_id: order.orderId,
    prefill: {
      email: user?.email || '',
      name: user?.name || '',
    },
    theme: { color: '#6344E7' },
    handler: (response) => {
      onSuccess?.(response);
    },
    modal: {
      ondismiss: () => onError?.(new Error('Payment cancelled')),
    },
  };
  if (hideUpi) {
    // UPI and netbanking settle domestically, so neither can fund a
    // foreign-currency order. Cards are the international rail.
    options.config = {
      display: {
        hide: [{ method: 'upi' }, { method: 'netbanking' }],
      },
    };
    options.method = currency === 'INR'
      ? { upi: false, card: true, netbanking: true, wallet: false }
      : { card: true, upi: false, netbanking: false, wallet: false };
  }
  const rzp = new Razorpay(options);
  rzp.on('payment.failed', (response) => {
    onError?.(new Error(response.error?.description || 'Payment failed'));
  });
  rzp.open();
}
