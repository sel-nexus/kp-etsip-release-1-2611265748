/** Exercise application discovery through the running UI and real API. */
import { test, expect } from '../frontend/node_modules/@playwright/test';
import { loadEnv } from '../frontend/node_modules/vite';
import path from 'node:path';

const env = { ...loadEnv('development', path.resolve(import.meta.dirname, '../backend'), ''), ...process.env };

test('scoped user filters applications and follows portfolio drilldown', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('requestfailed', request => errors.push(`${request.url()}: ${request.failure()?.errorText}`));
  const password = env.E2E_DEMO_PASSWORD || env.SEED_DEMO_PASSWORD;
  expect(password, 'Set E2E_DEMO_PASSWORD or SEED_DEMO_PASSWORD').toBeTruthy();
  await page.goto('/login');
  await page.getByLabel('Email').fill('readonly@ketsip.local');
  await page.getByLabel('Password', { exact: true }).fill(password!);
  const login = page.waitForResponse(r => r.url().endsWith('/api/auth/login') && r.request().method() === 'POST');
  const initial = page.waitForResponse(r => r.url().includes('/api/applications?') && r.request().method() === 'GET');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  expect((await login).status()).toBe(200);
  const initialResponse = await initial;
  expect(initialResponse.status()).toBe(200);
  const inventory = await initialResponse.json();
  expect(inventory.total).toBeGreaterThan(0);
  const selected = inventory.items[0];
  await expect(page.getByRole('link', { name: selected.name, exact: true })).toBeVisible();
  await page.getByLabel('Search applications').fill(selected.name);
  const filtered = page.waitForResponse(r => r.url().includes('/api/applications?') && r.url().includes('search='));
  await page.getByRole('button', { name: 'Apply filters' }).click();
  const filteredResponse = await filtered;
  expect(filteredResponse.status()).toBe(200);
  expect((await filteredResponse.json()).items.some((row: { id: string }) => row.id === selected.id)).toBe(true);
  const detail = page.waitForResponse(r => r.url().endsWith(`/api/applications/${selected.id}`));
  await page.getByRole('link', { name: selected.name, exact: true }).click();
  expect((await detail).status()).toBe(200);
  await expect(page.getByRole('heading', { name: selected.name })).toBeVisible();
  await expect(page.getByText(selected.businessOwner, { exact: true })).toBeVisible();
  await page.getByRole('link', { name: selected.portfolioName, exact: true }).click();
  await expect(page.getByRole('heading', { name: selected.portfolioName })).toBeVisible();
  await expect(page.getByRole('link', { name: selected.name, exact: true })).toBeVisible();
  await page.getByRole('link', { name: selected.name, exact: true }).click();
  await expect(page.getByRole('heading', { name: selected.name })).toBeVisible();
  expect(errors).toEqual([]);
});
