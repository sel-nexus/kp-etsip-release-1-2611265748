/** Exercise application creation, editing, and deletion against the live API. */
import { test, expect } from '../frontend/node_modules/@playwright/test/index.mjs';

test('administrator creates, edits, re-queries and deletes an application', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('requestfailed', request => errors.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`));
  expect(process.env.E2E_ADMIN_PASSWORD, 'Set E2E_ADMIN_PASSWORD to an already-rotated admin password.').toBeTruthy();
  await page.addInitScript(() => { (window as Window & { __inventoryXss?: boolean }).__inventoryXss = false; });
  await page.goto('/login');
  await page.getByLabel('Email').fill('admin@ketsip.local');
  await page.getByLabel('Password', { exact: true }).fill(process.env.E2E_ADMIN_PASSWORD!);
  const login = page.waitForResponse(r => r.url().endsWith('/api/auth/login') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  const loginResponse = await login;
  expect(loginResponse.status()).toBe(200);
  const { token } = await loginResponse.json();
  expect(token).toBeTruthy();
  await page.getByRole('link', { name: 'Applications', exact: true }).click();
  await page.getByRole('link', { name: 'Create application' }).click();
  const name = `Application journey ${Date.now()}-${test.info().project.name}`;
  await page.getByLabel('Name', { exact: true }).fill(name);
  const xss = '<img src=x onerror="window.__inventoryXss = true">';
  await page.getByLabel('Description', { exact: true }).fill(xss);
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
    expect(item.description).toBe(xss);
    await expect(page.getByRole('heading', { name })).toBeVisible();
    const details = page.getByRole('region', { name: 'Application details' });
    await expect(details.getByText(xss, { exact: true })).toBeVisible();
    await expect(details.locator('img')).toHaveCount(0);
    expect(await page.evaluate(() => (window as Window & { __inventoryXss?: boolean }).__inventoryXss)).toBe(false);
    await page.getByRole('link', { name: 'Edit application' }).click();
    await page.getByLabel('Quality score').fill('87');
    const updated = page.waitForResponse(r => r.url().endsWith(`/api/applications/${item.id}`) && r.request().method() === 'PUT');
    await page.getByRole('button', { name: 'Save application' }).click();
    expect((await updated).status()).toBe(200);
    await expect(page.getByRole('heading', { name })).toBeVisible();
    await expect(page.getByText('87', { exact: true })).toBeVisible();
    // StrictMode can issue a second detail GET; let it finish before reload cancels the document.
    await page.waitForLoadState('networkidle');
    await page.reload();
    await expect(page.getByText('87', { exact: true })).toBeVisible();
    await expect(details.getByText(xss, { exact: true })).toBeVisible();
    await expect(details.locator('img')).toHaveCount(0);
    expect(await page.evaluate(() => (window as Window & { __inventoryXss?: boolean }).__inventoryXss)).toBe(false);
    await page.getByRole('button', { name: 'Delete application' }).click();
    const deleted = page.waitForResponse(r => r.url().endsWith(`/api/applications/${item.id}`) && r.request().method() === 'DELETE');
    await page.getByRole('button', { name: 'Confirm delete' }).click();
    expect((await deleted).status()).toBe(204);
    await expect(page.getByText('Application deleted.')).toBeVisible();
    expect(errors).toEqual([]);
  } finally {
    const existing = await page.request.get(`/api/applications/${item.id}`, { headers: { Authorization: `Bearer ${token}` } });
    expect([200, 404], 'Application cleanup lookup must return 200 or 404').toContain(existing.status());
    if (existing.status() === 200) {
      expect((await page.request.delete(`/api/applications/${item.id}`, { headers: { Authorization: `Bearer ${token}` } })).status()).toBe(204);
      const afterDelete = await page.request.get(`/api/applications/${item.id}`, { headers: { Authorization: `Bearer ${token}` } });
      expect(afterDelete.status(), 'Application must be absent after cleanup').toBe(404);
    }
  }
});
