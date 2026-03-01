/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary:   { DEFAULT: "#6366f1", dark: "#4338ca" },
        surface:   { DEFAULT: "#1e1e2e", light: "#2a2a3e" },
        accent:    { DEFAULT: "#22d3ee", warm: "#f59e0b" },
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
