import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/**
 * Substitutes the active label's branding into index.html at transform time, so
 * the tab title and favicon are correct on first paint rather than being patched
 * in by React after mount.
 *
 * src/generated/label.json is produced by `make label` and committed (resolved
 * freshmart), so this works without having run anything first.
 */
function labelHtml(): Plugin {
  return {
    name: 'demo-label-html',
    transformIndexHtml(html) {
      const labelPath = resolve(__dirname, 'src/generated/label.json')
      const { brand } = JSON.parse(readFileSync(labelPath, 'utf-8'))
      return html
        .replace(/%LABEL_TAB_TITLE%/g, brand.tab_title)
        .replace(/%LABEL_FAVICON%/g, brand.favicon)
    },
  }
}

export default defineConfig({
  plugins: [react(), labelHtml()],
  server: {
    host: '0.0.0.0',
    port: 5173,
  },
})
