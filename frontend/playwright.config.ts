import { defineConfig, devices } from '@playwright/test'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const python = path.join(
  root,
  'backend',
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
)
const data = mkdtempSync(path.join(tmpdir(), 'headcount-e2e-'))
// Never reuse the user's application or database; use separate ports by default.
const apiPort = Number(process.env.HEADCOUNT_E2E_API_PORT ?? 18000)
const webPort = Number(process.env.HEADCOUNT_E2E_WEB_PORT ?? 15173)
if (
  [apiPort, webPort].some((port) => !Number.isInteger(port) || port < 1024 || port > 65535) ||
  apiPort === webPort
) {
  throw new Error('E2E ports must be distinct integers between 1024 and 65535')
}
const apiURL = `http://127.0.0.1:${apiPort}`
const webURL = `http://127.0.0.1:${webPort}`

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  use: { baseURL: webURL, trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:create_app --factory --app-dir "${path.join(root, 'backend')}" --host 127.0.0.1 --port ${apiPort}`,
      url: `${apiURL}/api/health`,
      reuseExistingServer: false,
      env: { HEADCOUNT_DATA_DIR: data, HEADCOUNT_MODEL_PATH: path.join(data, 'missing.onnx') },
    },
    {
      command: 'npm run dev',
      url: webURL,
      reuseExistingServer: false,
      env: { HEADCOUNT_DEV_PORT: String(webPort), HEADCOUNT_API_TARGET: apiURL },
    },
  ],
})
