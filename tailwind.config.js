/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './templates/**/*.html',
    './core/**/*.py',
  ],
  theme: {
    extend: {
      colors: {
        dark: {
          900: '#000000',
          800: '#0a0a0a',
          700: '#141414',
          600: '#1a1a1a',
          500: '#262626',
          400: '#333333',
        },
        accent: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
}
