/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: '#0F1B2D', 900: '#0B1524', 800: '#0F1B2D', 700: '#15243A', 600: '#1B2D47', 500: '#24364F', 400: '#556E94' },
        paper: { DEFAULT: '#E7EEF6', dim: '#A9B8CC', mute: '#8FA1BA' },
        contour: { DEFAULT: '#4FC3C7', soft: '#2E7F86', glow: '#8FE3E6' },
        survey: { DEFAULT: '#F0A04B', soft: '#9A6631' },
        ok: '#6CCB8B', warn: '#F0A04B', bad: '#EF6F6C',
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      fontSize: { '2xs': ['0.75rem', '1rem'] },
    },
  },
  plugins: [],
}
