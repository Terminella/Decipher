
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: '#17A6A1',
          dark: '#11817E',
          light: '#DDF5F2',
        },
        navy: {
          DEFAULT: '#17243A',
          light: '#243650',
        },
        accent: {
          purple: '#7566D9',
          amber: '#EAA34B',
          coral: '#E56B78',
        },
      },
    },
  },
  plugins: [],
}
