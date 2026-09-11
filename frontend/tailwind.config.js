/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: {
          DEFAULT: '#090d16',
          card: '#101624',
          panel: '#131b2c',
          elevated: '#172236',
          stone: '#1b2438',
        },
        tactical: {
          border: 'rgba(148, 163, 184, 0.15)',
          grid: 'rgba(148, 163, 184, 0.04)',
          muted: '#64748b',
          light: '#94a3b8',
          bright: '#e2e8f0',
        },
        severity: {
          critical: '#dc2626',
          high: '#ea580c',
          warning: '#d97706',
          normal: '#16a34a',
          info: '#0284c7',
          gis: '#0f766e',
          ai: '#38bdf8',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Courier New', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'radar-sweep': 'radarSweep 6s linear infinite',
      },
      keyframes: {
        radarSweep: {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' },
        },
      },
    },
  },
  plugins: [],
}
