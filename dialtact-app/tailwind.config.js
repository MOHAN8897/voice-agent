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
        /*
         * Semantic design tokens (see src/console/DESIGN.md). New and restyled code
         * uses ONLY these; the legacy keys above stay so existing callers keep working.
         * Values are mirrored as CSS variables in src/styles/globals.css.
         */
        canvas: '#FAF9FD',
        ink: '#0F0E17',
        fg: {
          DEFAULT: '#0F0E17',
          body: '#524E5E',
          muted: '#716C7F',
          subtle: '#8C879A',
          inverse: '#FFFFFF',
        },
        line: {
          DEFAULT: '#E4E2EB',
          strong: '#D1CFDB',
        },
        accent: {
          DEFAULT: '#6344E7',
          hover: '#5234D4',
          soft: '#F0ECFF',
          fg: '#5034CE',
        },
        success: { DEFAULT: '#10B981', soft: '#ECFDF5', fg: '#047857', line: '#A7F3D0' },
        warning: { DEFAULT: '#F59E0B', soft: '#FFFBEB', fg: '#92400E', line: '#FDE68A' },
        danger: { DEFAULT: '#EF4444', soft: '#FEF2F2', fg: '#B91C1C', line: '#FECACA' },
        info: { DEFAULT: '#3B82F6', soft: '#EFF6FF', fg: '#1E40AF', line: '#BFDBFE' },
        neutral: { DEFAULT: '#8C879A', soft: '#F4F3F8', fg: '#524E5E', line: '#E4E2EB' },
      },
      /* Type scale: 12px is the floor. Use text-meta for timestamps/captions. */
      fontSize: {
        meta: ['12px', { lineHeight: '16px' }],
        ui: ['13px', { lineHeight: '20px' }],
        copy: ['14px', { lineHeight: '22px' }],
        title: ['16px', { lineHeight: '24px', fontWeight: '600' }],
        heading: ['20px', { lineHeight: '28px', fontWeight: '700', letterSpacing: '-0.02em' }],
        display: ['24px', { lineHeight: '32px', fontWeight: '700', letterSpacing: '-0.025em' }],
      },
      /* Three radii only: controls, cards, pills. */
      borderRadius: {
        control: '10px',
        card: '16px',
        pill: '9999px',
      },
      fontFamily: {
        sans: ['Inter', 'Plus Jakarta Sans', 'system-ui', '-apple-system', 'sans-serif'],
        display: ['Inter', 'Plus Jakarta Sans', 'sans-serif'],
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
