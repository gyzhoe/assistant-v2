import type { Config } from 'tailwindcss'

export default {
  content: ['./src/**/*.{ts,tsx,html}'],
  theme: {
    extend: {
      colors: {
        // Accent colour matches the --accent CSS variable used across all surfaces
        accent: {
          DEFAULT: '#0969da',
          light: '#2b88d8',
          dark: '#005a9e',
          hover: '#106ebe',
        },
        neutral: {
          50: '#faf9f8',
          100: '#f3f2f1',
          200: '#edebe9',
          300: '#d2d0ce',
          400: '#a19f9d',
          500: '#605e5c',
          600: '#484644',
          700: '#3b3a39',
          800: '#323130',
          900: '#201f1e',
        },
      },
      fontFamily: {
        sans: ['Segoe UI', 'system-ui', 'sans-serif'],
      },
      animation: {
        shimmer: 'shimmer 1.5s infinite',
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
    },
  },
  plugins: [],
} satisfies Config
