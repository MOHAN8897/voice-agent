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

export async function openRazorpayWalletCheckout({ order, keyId, user, onSuccess, onError }) {
  const Razorpay = await loadRazorpayScript();
  const rzp = new Razorpay({
    key: order.keyId || keyId,
    amount: order.amountPaise,
    currency: order.currency || 'INR',
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
  });
  rzp.on('payment.failed', (response) => {
    onError?.(new Error(response.error?.description || 'Payment failed'));
  });
  rzp.open();
}
