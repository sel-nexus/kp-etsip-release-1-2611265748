/** Exercise dashboard filters and backend-derived content through the real UI. */
import { test, expect } from '../frontend/node_modules/@playwright/test';
import { loadEnv } from '../frontend/node_modules/vite';
import path from 'node:path';

const env = { ...loadEnv('development', path.resolve(import.meta.dirname, '../backend'), ''), ...process.env };

test('executive filters live dashboard values', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  const password = env.E2E_DEMO_PASSWORD || env.SEED_DEMO_PASSWORD;
  expect(password, 'Set E2E_DEMO_PASSWORD or SEED_DEMO_PASSWORD').toBeTruthy();
  await page.goto('/');
  await page.getByRole('link', { name: 'Sign in' }).click();
  await page.getByLabel('Email').fill('executive@ketsip.local');
  await page.getByLabel('Password', { exact: true }).fill(password!);
  const initial = page.waitForResponse(response => response.url().endsWith('/api/dashboard/executive'));
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  const first = await initial;
  expect(first.status()).toBe(200);
  const data = await first.json();
  await expect(page.getByRole('heading', { name: 'Executive dashboard' })).toBeVisible();
  await expect(page.getByRole('article').filter({ hasText: 'Total Applications' })).toContainText(String(data.totalApplications));
  await page.getByLabel('Risk level filter').selectOption('High');
  const filtered = page.waitForResponse(response => response.url().includes('/api/dashboard/executive?') && response.url().includes('riskLevel=High'));
  await page.getByRole('button', { name: 'Apply filters' }).click();
  const result = await filtered;
  expect(result.status()).toBe(200);
  const body = await result.json();
  await expect(page.getByRole('article').filter({ hasText: 'Applications at Risk' })).toContainText(String(body.applicationsAtRisk));
  await expect(page.getByRole('article').filter({ hasText: 'Total Applications' })).toContainText(String(body.totalApplications));
  expect(body.applicationsAtRisk).toBe(body.totalApplications);
  expect(page.url()).toContain('riskLevel=High');
  expect(errors).toEqual([]);
});
