import type { Config } from 'tailwindcss';

/** BrainOS — light gradient purple primary, system fonts (no external fetch at build). */
const config: Config = {
  content: ['./app/**/*.{js,ts,jsx,tsx}', './components/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        primary: '#7c3aed',
        'primary-light': '#a78bfa',
        'primary-dark': '#6d28d9',
        violet: {
          50: '#f5f3ff',
          100: '#ede9fe',
          200: '#ddd6fe',
          300: '#c4b5fd',
          400: '#a78bfa',
          500: '#8b5cf6',
          600: '#7c3aed',
          700: '#6d28d9',
          800: '#5b21b6',
          900: '#4c1d95',
        },
        'background-light': '#faf5ff',
        'background-dark': '#1e1b4b',
        theme: {
          surface: '#ede9fe',
          muted: '#64748b',
          success: '#059669',
          warning: '#d97706',
          danger: '#e11d48',
        },
        brain: {
          bg: '#faf5ff',
          surface: '#ede9fe',
          card: '#ffffff',
          border: '#e9e5f0',
          primary: '#7c3aed',
          primaryHover: '#6d28d9',
          accent: '#8b5cf6',
          success: '#059669',
          warning: '#d97706',
          danger: '#e11d48',
          text: '#1e1b4b',
          muted: '#64748b',
          link: '#7c3aed',
          pastel: {
            peach: '#fce7f3',
            mint: '#d1fae5',
            lavender: '#ede9fe',
            cream: '#faf5ff',
          },
        },
      },
      fontFamily: {
        display: ['system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        sans: ['system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        mono: ['ui-monospace', 'monospace'],
      },
      borderRadius: {
        DEFAULT: '0.25rem',
        lg: '0.5rem',
        xl: '0.75rem',
        '2xl': '1rem',
        full: '9999px',
      },
      boxShadow: {
        soft: '0 2px 12px rgba(124, 58, 237, 0.06)',
        card: '0 1px 4px rgba(124, 58, 237, 0.08)',
        glass: '0 8px 32px rgba(124, 58, 237, 0.12), 0 2px 8px rgba(0,0,0,0.04)',
        'glass-lg': '0 16px 48px rgba(124, 58, 237, 0.15), 0 4px 16px rgba(0,0,0,0.06)',
      },
      backgroundImage: {
        'primary-gradient': 'linear-gradient(135deg, #c4b5fd 0%, #a78bfa 50%, #7c3aed 100%)',
        'primary-gradient-subtle': 'linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%)',
        'page-gradient': 'linear-gradient(to bottom right, #faf5ff 0%, #f5f3ff 50%, #ede9fe 100%)',
      },
      backdropBlur: {
        xs: '2px',
      },
    },
  },
  plugins: [],
};
export default config;
