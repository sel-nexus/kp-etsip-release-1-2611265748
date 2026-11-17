/** Configure live auth journeys; execution is owned by the parent verification phase. */
import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';
import { assertLocalMongo, e2eApiUrl, e2eDatabase, e2eMongoUri, e2ePython } from './scripts/e2e-setup';
const tier = path.resolve(import.meta.dirname);
const env = process.env;
const baseURL = env.E2E_BASE_URL || 'http://127.0.0.1:5173';
const apiURL = env.E2E_API_URL || 'http://127.0.0.1:8000';
// Never attach fixtures to an existing or remote server whose database is unknown.
assertLocalMongo();
if (baseURL !== 'http://127.0.0.1:5173' || apiURL !== e2eApiUrl) {
  throw new Error('E2E requires its own local frontend and backend on ports 5173 and 8000.');
}
const names = ['E2E_JWT_SECRET', 'E2E_SEED_ADMIN_PASSWORD', 'E2E_ADMIN_PASSWORD', 'E2E_DEMO_PASSWORD'] as const;
const secrets = names.map(name => {
  const value = process.env[name];
  if (!value || !/^[A-Za-z0-9_-]{32,72}$/.test(value)) throw new Error(`${name} must be a freshly generated 32–72 character URL-safe test-only secret.`);
  return value;
});
if (new Set(secrets).size !== secrets.length) throw new Error('E2E secrets must be distinct.');
// Specs use several names for the same seed password; override any inherited values.
Object.assign(process.env, {
  E2E_EMAIL: 'executive@ketsip.local', E2E_PASSWORD: secrets[3],
  E2E_EXECUTIVE_PASSWORD: secrets[3], E2E_READONLY_PASSWORD: secrets[3],
  E2E_AUDITOR_PASSWORD: secrets[3], SEED_DEMO_PASSWORD: secrets[3],
});

// The server is launched from the frontend directory, never from backend/.env.
// The operator guarantees no external clients; collection creation arbitrates same-ID runners.
const launch = `
import os, sys
from pymongo import MongoClient
client = MongoClient(os.environ['MONGODB_URI'], serverSelectionTimeoutMS=5000)
try:
    name = os.environ['MONGODB_DB']
    if name in client.list_database_names():
        raise RuntimeError('E2E database already exists; choose a fresh E2E_RUN_ID')
    db = client[name]
    if db.list_collection_names():
        raise RuntimeError('E2E database is not empty; refusing to seed')
    reservation = db.create_collection('e2e_reservation')
    reservation.insert_one({'_id': os.environ['E2E_RUN_ID']})
    if set(db.list_collection_names()) != {'e2e_reservation'}:
        raise RuntimeError('E2E database contains unexpected collections; refusing to seed')
    if reservation.count_documents({}) != 1 or not reservation.find_one({'_id': os.environ['E2E_RUN_ID']}):
        raise RuntimeError('E2E database reservation is not exclusively owned; refusing to seed')
finally:
    client.close()
os.execv(sys.executable, [sys.executable, '-m', 'uvicorn', 'app.main:app', '--app-dir', os.environ['E2E_BACKEND_DIR'], '--host', '127.0.0.1', '--port', '8000'])
`;
const shellQuote = (value: string) => `'${value.replace(/'/g, `'\\''`)}'`;
export default defineConfig({
  testDir: '../e2e',
  globalSetup: './scripts/e2e-setup.ts',
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
      command: `${shellQuote(e2ePython)} -c ${shellQuote(launch)}`,
      cwd: tier, url: `${apiURL}/api/health`, reuseExistingServer: false,
      env: {
        E2E_BACKEND_DIR: path.resolve(tier, '../backend'), E2E_RUN_ID: env.E2E_RUN_ID!,
        MONGODB_URI: e2eMongoUri, MONGODB_DB: e2eDatabase, APP_ENV: 'test',
        JWT_SECRET: secrets[0], SEED_ADMIN_PASSWORD: secrets[1], SEED_DEMO_PASSWORD: secrets[3],
        SEED_ON_STARTUP: 'true', CORS_ORIGINS: '', JWT_EXPIRY_HOURS: '8', HOST: '127.0.0.1', PORT: '8000',
      }, timeout: 60000,
    },
    {
      command: 'node node_modules/vite/bin/vite.js', cwd: tier, url: baseURL,
      reuseExistingServer: false, env: { API_PROXY_TARGET: e2eApiUrl, VITE_API_BASE_URL: '/api', DEV_HOST: '127.0.0.1', DEV_PORT: '5173' }, timeout: 60000,
    },
  ],
});
