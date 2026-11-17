/** Exercise real user management via the browser; execution is deferred. */
import { test, expect } from '../frontend/node_modules/@playwright/test/index.mjs';
import { randomBytes } from 'node:crypto';

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
  const portfolioResponse = await page.request.get('/api/portfolios?pageSize=100', { headers: { Authorization: `Bearer ${session.token}` } });
  expect(portfolioResponse.status()).toBe(200);
  const portfolios = (await portfolioResponse.json()).items as { id: string; name: string }[];
  expect(portfolios.length, 'At least two portfolios are needed to exercise reassignment').toBeGreaterThanOrEqual(2);
  await page.getByRole('link', { name: 'Administration' }).click();
  await page.getByRole('button', { name: 'Create user' }).click();
  const email = `journey-${Date.now()}-${test.info().parallelIndex}@example.com`;
  const testPassword = `Aa1!${randomBytes(24).toString('base64url')}`;
  await page.getByLabel('Name', { exact: true }).fill('Journey User');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(testPassword);
  await page.getByLabel('Role', { exact: true }).selectOption('Engineer');
  await page.getByRole('checkbox', { name: portfolios[0].name, exact: true }).check();
  const created = page.waitForResponse(response => response.url().endsWith('/api/users') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Save user' }).click();
  const response = await created;
  expect(response.status()).toBe(201);
  const account = await response.json();
  try {
    expect(account.email).toBe(email);
    expect(account.role).toBe('Engineer');
    expect(account.portfolioAccess).toEqual([portfolios[0].id]);
    const persistedCreate = await page.request.get(`/api/users/${account.id}`, { headers: { Authorization: `Bearer ${session.token}` } });
    expect(persistedCreate.status()).toBe(200);
    expect(await persistedCreate.json()).toMatchObject({ role: 'Engineer', portfolioAccess: [portfolios[0].id] });
    await page.getByLabel('Search users').fill(email);
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    await expect(page.getByText(email)).toBeVisible();
    await page.getByRole('button', { name: 'Edit Journey User' }).click();
    await page.getByLabel('Name', { exact: true }).fill('Journey Updated');
    await expect(page.getByLabel('Role', { exact: true })).toHaveValue('Engineer');
    await expect(page.getByRole('checkbox', { name: portfolios[0].name, exact: true })).toBeChecked();
    await page.getByLabel('Role', { exact: true }).selectOption('Portfolio Leader');
    await page.getByRole('checkbox', { name: portfolios[0].name, exact: true }).uncheck();
    await page.getByRole('checkbox', { name: portfolios[1].name, exact: true }).check();
    const updated = page.waitForResponse(r => r.url().endsWith(`/api/users/${account.id}`) && r.request().method() === 'PUT');
    await page.getByRole('button', { name: 'Save user' }).click();
    const updateResponse = await updated;
    expect(updateResponse.status()).toBe(200);
    expect(await updateResponse.json()).toMatchObject({ name: 'Journey Updated', role: 'Portfolio Leader', portfolioAccess: [portfolios[1].id] });
    const persistedUpdate = await page.request.get(`/api/users/${account.id}`, { headers: { Authorization: `Bearer ${session.token}` } });
    expect(persistedUpdate.status()).toBe(200);
    expect(await persistedUpdate.json()).toMatchObject({ name: 'Journey Updated', role: 'Portfolio Leader', portfolioAccess: [portfolios[1].id] });
    await expect(page.getByRole('table', { name: 'Users' }).getByRole('cell', { name: 'Journey Updated', exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByRole('table', { name: 'Users' }).getByRole('cell', { name: 'Journey Updated', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Edit Journey Updated' }).click();
    await expect(page.getByLabel('Role', { exact: true })).toHaveValue('Portfolio Leader');
    await expect(page.getByRole('checkbox', { name: portfolios[0].name, exact: true })).not.toBeChecked();
    await expect(page.getByRole('checkbox', { name: portfolios[1].name, exact: true })).toBeChecked();
    await page.getByRole('button', { name: 'Cancel', exact: true }).click();
    await page.getByRole('button', { name: 'Deactivate Journey Updated' }).click();
    const removed = page.waitForResponse(r => r.url().endsWith(`/api/users/${account.id}`) && r.request().method() === 'DELETE');
    await page.getByRole('button', { name: 'Confirm delete' }).click();
    expect((await removed).status()).toBe(204);
    await expect(page.getByText('User deactivated.')).toBeVisible();
    expect(errors).toEqual([]);
  } finally {
    const record = await page.request.get(`/api/users/${account.id}`, { headers: { Authorization: `Bearer ${session.token}` } });
    expect([200, 404], 'Cleanup lookup must find the account or confirm it is absent').toContain(record.status());
    if (record.status() === 200) {
      const current = await record.json();
      expect(['Active', 'Inactive'], 'Cleanup lookup returned an unexpected account status').toContain(current.status);
      if (current.status === 'Active') {
        const deactivated = await page.request.delete(`/api/users/${account.id}`, { headers: { Authorization: `Bearer ${session.token}` } });
        expect(deactivated.status(), 'Cleanup deactivation must succeed').toBe(204);
      }
      const verified = await page.request.get(`/api/users/${account.id}`, { headers: { Authorization: `Bearer ${session.token}` } });
      expect(verified.status(), 'Cleanup verification must find the account').toBe(200);
      expect((await verified.json()).status, 'Cleanup must leave the account inactive').toBe('Inactive');
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
