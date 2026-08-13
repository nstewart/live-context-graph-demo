import colors from 'tailwindcss/colors'
import label from './src/generated/label.json'

// The brand color is label-driven. Source uses `brand-*` / `accent-*` classes
// throughout instead of a hardcoded palette, so a label swap re-themes the UI
// without touching components.
//
// `brand`  - primary identity: wordmark, active nav, primary buttons, focus rings
// `accent` - the semantic/vector-search accent (triples, embeddings, rerank)
const palette = (name, fallback) => colors[name] ?? colors[fallback]

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: palette(label.brand.theme.primary, 'green'),
        accent: palette(label.brand.theme.accent, 'purple'),
      },
    },
  },
  plugins: [],
}
