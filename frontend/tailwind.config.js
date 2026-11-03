/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        ocean: {
          950: '#060a12',
          900: '#0b1329',
          850: '#111c38',
          800: '#16223f',
          750: '#1d2a4d',
          700: '#223259',
          600: '#33487a',
          500: '#0ea5e9',
          400: '#38bdf8',
        }
      }
    },
  },
  plugins: [],
}

