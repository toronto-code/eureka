import { promises as fs } from 'fs'
import path from 'path'

const DATA_DIR = path.join(process.cwd(), 'data')

async function ensureDir() {
  try { await fs.mkdir(DATA_DIR, { recursive: true }) } catch {}
}

export async function readStore<T>(name: string, fallback: T): Promise<T> {
  try {
    const raw = await fs.readFile(path.join(DATA_DIR, `${name}.json`), 'utf-8')
    return JSON.parse(raw)
  } catch {
    return fallback
  }
}

export async function writeStore<T>(name: string, data: T): Promise<void> {
  await ensureDir()
  await fs.writeFile(path.join(DATA_DIR, `${name}.json`), JSON.stringify(data, null, 2))
}
