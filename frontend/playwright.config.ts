/** Configure live auth journeys; execution is owned by the parent verification phase. */
import { defineConfig, devices } from '@playwright/test';
import { loadEnv } from 'vite';
import path from 'node:path';
const tier = path.resolve(import.meta.dirname);
const env = { ...loadEnv('development', tier, ''), ...process.env };
const baseURL = env.E2E_BASE_URL || 'http://127.0.0.1:5173';
const apiURL = env.E2E_API_URL || 'http://127.0.0.1:8000';
export default defineConfig({
  testDir: '../e2e',
  timeout: 30000,
  workers: 1,
  retries: 0,
  use: { baseURL, trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
  webServer: [
    {
      command: '"$HOME/venvs/etsip/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000',
      cwd: path.resolve(tier, '../backend'), url: `${apiURL}/api/health`, reuseExistingServer: true,
      env: { MONGODB_DB: 'etsip_e2e', APP_ENV: 'development' }, timeout: 60000,
    },
    {
      command: 'node node_modules/vite/bin/vite.js', cwd: tier, url: baseURL,
      reuseExistingServer: true, timeout: 60000,
    },
  ],
});
