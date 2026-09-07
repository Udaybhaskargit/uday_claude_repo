/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          900: "#0f1b30",
          950: "#0a121f",
        },
        amber: {
          400: "#f0b85c",
          500: "#e8a33d",
        },
        slate: {
          100: "#f5f7fa",
          300: "#c7d0dc",
          500: "#8391a6",
          700: "#4b5670",
        },
      },
    },
  },
  plugins: [],
};
