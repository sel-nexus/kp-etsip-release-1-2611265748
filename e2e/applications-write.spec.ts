/** Exercise application creation, editing, and deletion against the live API. */
import { test, expect } from '../frontend/node_modules/@playwright/test';
import { loadEnv } from '../frontend/node_modules/vite';
import path from 'node:path';

const env = { ...loadEnv('development', path.resolve(import.meta.dirname, '../backend'), ''), ...process.env };

test('administrator creates, edits, re-queries and deletes an application', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('requestfailed', request => errors.push(`${request.method()} ${request.url()}`));
  expect(env.E2E_ADMIN_PASSWORD, 'Set E2E_ADMIN_PASSWORD to an already-rotated admin password.').toBeTruthy();
  await page.goto('/login');
  await page.getByLabel('Email').fill('admin@ketsip.local');
  await page.getByLabel('Password', { exact: true }).fill(env.E2E_ADMIN_PASSWORD!);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.getByRole('link', { name: 'Applications', exact: true }).click();
  await page.getByRole('link', { name: 'Create application' }).click();
  const name = `Application journey ${Date.now()}-${test.info().project.name}`;
  await page.getByLabel('Name', { exact: true }).fill(name);
  const portfolio = page.getByLabel('Portfolio', { exact: true });
  const options = await portfolio.locator('option').count();
  expect(options).toBeGreaterThan(1);
  await portfolio.selectOption({ index: 1 });
  const created = page.waitForResponse(response => response.url().endsWith('/api/applications') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Save application' }).click();
  const response = await created;
  expect(response.status()).toBe(201);
  const item = await response.json();
  try {
    await expect(page.getByRole('heading', { name })).toBeVisible();
    await page.getByRole('link', { name: 'Edit application' }).click();
    await page.getByLabel('Quality score').fill('87');
    const updated = page.waitForResponse(r => r.url().endsWith(`/api/applications/${item.id}`) && r.request().method() === 'PUT');
    await page.getByRole('button', { name: 'Save application' }).click();
    expect((await updated).status()).toBe(200);
    await page.reload();
    await expect(page.getByText('87', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Delete application' }).click();
    const deleted = page.waitForResponse(r => r.url().endsWith(`/api/applications/${item.id}`) && r.request().method() === 'DELETE');
    await page.getByRole('button', { name: 'Confirm delete' }).click();
    expect((await deleted).status()).toBe(204);
    await expect(page.getByText('Application deleted.')).toBeVisible();
    expect(errors).toEqual([]);
  } finally {
    const token = await page.evaluate(() => localStorage.getItem('etsip.token'));
    const existing = await page.request.get(`/api/applications/${item.id}`, { headers: { Authorization: `Bearer ${token}` } });
    if (existing.status() === 200) expect((await page.request.delete(`/api/applications/${item.id}`, { headers: { Authorization: `Bearer ${token}` } })).status()).toBe(204);
  }
});
