/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['IBM Plex Sans', 'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['IBM Plex Mono', 'Fira Code', 'Consolas', 'monospace'],
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

        // ── IBM Carbon Blue, remapped onto Tailwind's `indigo` scale ──────────
        // The app's accent was hard-coded as `indigo-*` across ~19 files. Rather
        // than sweep every call site, we point `indigo` at Carbon's Blue ramp so
        // every existing `bg-indigo-600` / `text-indigo-500` becomes Carbon Blue.
        // Blue 60 (#0f62fe) is Carbon's primary interactive color.
        indigo: {
          50:  '#edf5ff',  // Blue 10
          100: '#d0e2ff',  // Blue 20
          200: '#a6c8ff',  // Blue 30
          300: '#a6c8ff',  // Blue 30  (light text on dark badges)
          400: '#78a9ff',  // Blue 40
          500: '#4589ff',  // Blue 50  (links / accents / button hover)
          600: '#0f62fe',  // Blue 60  (primary interactive)
          700: '#0353e9',  // Blue 70  (hover/active)
          800: '#0043ce',  // Blue 80  (dark badge surface)
          900: '#002d9c',  // Blue 90
          950: '#001d6c',  // Blue 100
        },
      },
      // ── Carbon is square. Flatten Tailwind's radius scale so every
      //    rounded-lg / rounded-xl / rounded-2xl / rounded-full reads as a
      //    crisp 2px corner instead of the previous pill/card softness. ──────
      borderRadius: {
        none:    '0',
        sm:      '0',
        DEFAULT: '2px',
        md:      '2px',
        lg:      '2px',
        xl:      '2px',
        '2xl':   '2px',
        '3xl':   '4px',
        full:    '2px',
      },
    },
  },
  plugins: [],
}
