/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
      colors: {
        // Semantic theme tokens — driven by CSS variables in index.css
        tbg:     'var(--t-bg)',
        tsurf:   'var(--t-surface)',
        tsurf2:  'var(--t-s2)',
        tborder: 'var(--t-border)',
        tb2:     'var(--t-b2)',
        t1:      'var(--t-1)',
        t2:      'var(--t-2)',
        t3:      'var(--t-3)',
        t4:      'var(--t-4)',
      },
    },
  },
  plugins: [],
}
