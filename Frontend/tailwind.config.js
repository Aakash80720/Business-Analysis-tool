/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary:   { DEFAULT: "#818cf8", hover: "#6366f1", dark: "#4338ca", muted: "rgba(129,140,248,0.12)" },
        surface:   { DEFAULT: "#18181b", light: "#27272a", hover: "#2e2e33" },
        accent:    { DEFAULT: "#22d3ee", warm: "#fbbf24", muted: "rgba(34,211,238,0.12)" },
        success:   "#34d399",
        warning:   "#fbbf24",
        danger:    "#f87171",
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      borderRadius: {
        '2xl': '16px',
        '3xl': '24px',
      },
      boxShadow: {
        glow: '0 0 20px -5px rgba(129,140,248,0.3)',
        'glow-lg': '0 0 40px -10px rgba(129,140,248,0.25)',
      },
      animation: {
        'fade-in': 'fadeIn 0.4s ease-out both',
        'slide-up': 'slideUp 0.5s ease-out both',
      },
      keyframes: {
        fadeIn: {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        slideUp: {
          from: { opacity: '0', transform: 'translateY(20px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
