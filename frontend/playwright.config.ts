import path from 'node:path'
import os from 'node:os'
import { defineConfig } from '@playwright/test'

// Browser tests of the real app: the backend on a throwaway SQLite file, without an AI model, and the Vite dev server in front of it.
//   PYTHON               the interpreter that has the backend's requirements (default: python3)
//   PLAYWRIGHT_CHROMIUM  a Chromium already on the machine, instead of the one `npx playwright install chromium` downloads
const API = 8123, WEB = 5179
const database = path.join(os.tmpdir(), `evs-e2e-${process.pid}.db`)

export default defineConfig({
  testDir: 'e2e',
  workers: 1, // the tests share one database, reset before each
  timeout: 30_000,
  reporter: 'list',
  use: { baseURL: `http://localhost:${WEB}`, launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM || undefined } },
  webServer: [
    {
      command: `${process.env.PYTHON ?? 'python3'} -m uvicorn app.main:app --port ${API}`,
      cwd: path.resolve(import.meta.dirname, '../backend'),
      url: `http://localhost:${API}/api/health`,
      env: { DATABASE_URL: `sqlite+pysqlite:///${database}`, EMBEDDINGS: 'hash', LLM_ENABLED: 'false' },
      reuseExistingServer: false,
    },
    { command: `npx vite --port ${WEB} --strictPort`, url: `http://localhost:${WEB}`, env: { API_TARGET: `http://localhost:${API}` }, reuseExistingServer: false },
  ],
})
