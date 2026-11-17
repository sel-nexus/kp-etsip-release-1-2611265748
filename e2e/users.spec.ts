/** Exercise real user management via the browser; execution is deferred. */
import { test, expect } from '../frontend/node_modules/@playwright/test';

test('administrator creates, edits and deactivates an account', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('requestfailed', request => errors.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`));
  const password = process.env.E2E_ADMIN_PASSWORD;
  expect(password, 'Set E2E_ADMIN_PASSWORD to a rotated administrator password').toBeTruthy();
  await page.goto('/login');
  await page.getByLabel('Email').fill('admin@ketsip.local');
  await page.getByLabel('Password', { exact: true }).fill(password!);
  const login = page.waitForResponse(response => response.url().endsWith('/api/auth/login') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  const loggedIn = await login;
  expect(loggedIn.status()).toBe(200);
  const session = await loggedIn.json();
  expect(session.user.mustChangePassword).toBe(false);
  await page.getByRole('link', { name: 'Administration' }).click();
  await page.getByRole('button', { name: 'Create user' }).click();
  const email = `journey-${Date.now()}-${test.info().parallelIndex}@example.com`;
  await page.getByLabel('Name', { exact: true }).fill('Journey User');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill('JourneyPassword123!');
  const created = page.waitForResponse(response => response.url().endsWith('/api/users') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Save user' }).click();
  const response = await created;
  expect(response.status()).toBe(201);
  const account = await response.json();
  expect(account.email).toBe(email);
  try {
    await page.getByLabel('Search users').fill(email);
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    await expect(page.getByText(email)).toBeVisible();
    await page.getByRole('button', { name: 'Edit Journey User' }).click();
    await page.getByLabel('Name', { exact: true }).fill('Journey Updated');
    const updated = page.waitForResponse(r => r.url().endsWith(`/api/users/${account.id}`) && r.request().method() === 'PUT');
    await page.getByRole('button', { name: 'Save user' }).click();
    expect((await updated).status()).toBe(200);
    await expect(page.getByText('Journey Updated')).toBeVisible();
    await page.reload();
    await expect(page.getByText('Journey Updated')).toBeVisible();
    await page.getByRole('button', { name: 'Deactivate Journey Updated' }).click();
    const removed = page.waitForResponse(r => r.url().endsWith(`/api/users/${account.id}`) && r.request().method() === 'DELETE');
    await page.getByRole('button', { name: 'Confirm delete' }).click();
    expect((await removed).status()).toBe(204);
    await expect(page.getByText('User deactivated.')).toBeVisible();
    expect(errors).toEqual([]);
  } finally {
    const record = await page.request.get(`/api/users/${account.id}`, { headers: { Authorization: `Bearer ${session.token}` } });
    if (record.ok() && (await record.json()).status === 'Active') {
      expect((await page.request.delete(`/api/users/${account.id}`, { headers: { Authorization: `Bearer ${session.token}` } })).status()).toBe(204);
    }
  }
});

test('read-only user sees no administration link and API denies access', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('requestfailed', request => errors.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`));
  const password = process.env.E2E_DEMO_PASSWORD;
  expect(password, 'Set E2E_DEMO_PASSWORD to the seeded demo password').toBeTruthy();
  await page.goto('/login');
  await page.getByLabel('Email').fill('readonly@ketsip.local');
  await page.getByLabel('Password', { exact: true }).fill(password!);
  const login = page.waitForResponse(r => r.url().endsWith('/api/auth/login') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  const response = await login;
  expect(response.status()).toBe(200);
  const session = await response.json();
  await expect(page.getByRole('link', { name: 'Administration' })).toHaveCount(0);
  const denied = await page.request.get('/api/users', { headers: { Authorization: `Bearer ${session.token}` } });
  expect(denied.status()).toBe(403);
  expect(errors).toEqual([]);
});
