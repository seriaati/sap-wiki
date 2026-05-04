import { cp, mkdir } from 'fs/promises'
import { existsSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const src = path.resolve(__dirname, '../../dumper/output/assets')
const dest = path.resolve(__dirname, '../public/assets')

if (existsSync(src)) {
  await mkdir(dest, { recursive: true })
  await cp(src, dest, { recursive: true })
  console.log('✓ Game assets copied to public/assets')
} else {
  console.log('→ No dumper/output/assets found, skipping')
}
