/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "var(--surface-chassis)",
          elevated: "var(--surface-panel)",
          card: "var(--surface-panel)",
          raised: "var(--surface-panel-raised)",
          panel: "var(--surface-panel)",
          "panel-raised": "var(--surface-panel-raised)",
          "panel-inset": "var(--surface-panel-inset)",
          chassis: "var(--surface-chassis)",
          glass: "var(--surface-glass)",
          border: "var(--border-subtle)",
          "border-subtle": "var(--border-subtle)",
        },
        accent: {
          DEFAULT: "var(--status-live)",
          primary: "var(--accent-primary)",
          dim: "var(--accent-primary-dim)",
          glow: "var(--accent-glow)",
          secondary: "var(--text-secondary)",
          hover: "#be123c",
        },
        text: {
          DEFAULT: "var(--text-primary)",
          muted: "var(--text-secondary)",
          subtle: "var(--text-muted)",
        },
        status: {
          success: "var(--status-success)",
          warning: "var(--status-warning)",
          error: "var(--status-error)",
          info: "var(--status-info)",
          live: "var(--status-live)",
        },
        success: "var(--status-success)",
        warning: "var(--status-warning)",
        "agent-online": "var(--status-live)",
        "agent-processing": "var(--text-secondary)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        display: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "20px",
        "skeuo-sm": "var(--radius-sm)",
        "skeuo-md": "var(--radius-md)",
        "skeuo-lg": "var(--radius-lg)",
      },
      maxWidth: {
        content: "72rem",
        shell: "88rem",
      },
      boxShadow: {
        card: "var(--shadow-raised)",
        "card-hover": "var(--shadow-floating)",
        glow: "0 0 40px -12px rgba(143, 166, 196, 0.35)",
        raised: "var(--shadow-raised)",
        inset: "var(--shadow-inset)",
        floating: "var(--shadow-floating)",
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
          "0%, 100%": { opacity: "0.45" },
          "50%": { opacity: "1" },
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
