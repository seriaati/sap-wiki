import { defineConfig } from 'astro/config'
import { fileURLToPath } from 'url'
import path from 'path'
import sitemap from '@astrojs/sitemap'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  site: 'https://sap.seria.moe',
  integrations: [sitemap()],
  vite: {
    resolve: {
      alias: {
        '@data': path.resolve(__dirname, '../dumper/output'),
      },
    },
  },
})
