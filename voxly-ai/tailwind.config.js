/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#FAF9FD',
        surface: '#FFFFFF',
        'surface-subtle': '#F0EEF6',
        'surface-dark': '#111019',
        text: {
          primary: '#0F0E17',
          secondary: '#524E5E',
          muted: '#524E5E',
          light: '#F0EEF6',
          darkMuted: '#A19EAD',
          darkSecondary: '#D1CFDB',
        },
        brand: {
          DEFAULT: '#6344E7',
          hover: '#5234D4',
          accent: '#8369F5',
          light: '#F0EEF6',
          dark: '#0F0E17',
        },
        border: {
          hairline: '#E4E2EB',
          dark: 'rgba(255, 255, 255, 0.08)',
        },
        telemetry: {
          green: '#10B981',
          amber: '#F59E0B',
          blue: '#3B82F6',
        },
      },
      fontFamily: {
        sans: ['Plus Jakarta Sans', 'Inter', 'system-ui', '-apple-system', 'sans-serif'],
        display: ['Plus Jakarta Sans', 'Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      boxShadow: {
        'craft-xs': '0 1px 2px rgba(15, 14, 23, 0.04)',
        'craft-sm': '0 1px 3px rgba(15, 14, 23, 0.05), 0 2px 8px rgba(15, 14, 23, 0.02)',
        'craft-md': '0 4px 16px rgba(15, 14, 23, 0.06), 0 1px 3px rgba(15, 14, 23, 0.03)',
        'craft-lg': '0 12px 36px rgba(15, 14, 23, 0.08), 0 2px 6px rgba(15, 14, 23, 0.04)',
      },
    },
  },
  plugins: [],
}
