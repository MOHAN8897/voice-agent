/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#09090b",
          elevated: "#0c0c0f",
          card: "#111113",
          raised: "#18181b",
          panel: "#0f0f12",
          border: "#27272a",
          "border-subtle": "#1c1c1f",
        },
        accent: {
          DEFAULT: "#e11d48",
          dim: "#1a0a10",
          glow: "#e11d4828",
          secondary: "#a1a1aa",
          hover: "#be123c",
        },
        text: { DEFAULT: "#f4f4f5", muted: "#a1a1aa", subtle: "#71717a" },
        success: "#22c55e",
        warning: "#f59e0b",
        "agent-online": "#e11d48",
        "agent-processing": "#a1a1aa",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        display: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: {
        sm: "8px",
        md: "12px",
        lg: "16px",
        xl: "24px",
      },
      maxWidth: {
        content: "72rem",
      },
      boxShadow: {
        card: "0 4px 24px -4px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(255, 255, 255, 0.04)",
        "card-hover": "0 12px 40px -8px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(225, 29, 72, 0.15)",
        glow: "0 0 60px -12px rgba(225, 29, 72, 0.45)",
      },
      animation: {
        "fade-up": "fade-up 0.7s cubic-bezier(0.22, 1, 0.36, 1) both",
        "fade-in": "fade-in 0.5s ease-out both",
        "pulse-soft": "pulse-soft 3s ease-in-out infinite",
        "pulse-dot": "pulse-dot 2s ease-in-out infinite",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(18px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "pulse-soft": {
          "0%, 100%": { opacity: "0.35" },
          "50%": { opacity: "0.9" },
        },
        "pulse-dot": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.55", transform: "scale(0.85)" },
        },
        wave: {
          "0%, 100%": { transform: "scaleY(0.45)" },
          "50%": { transform: "scaleY(1)" },
        },
      },
    },
  },
  plugins: [],
};
