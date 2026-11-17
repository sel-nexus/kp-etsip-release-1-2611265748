/** Exercise real administrator and auditor audit access; execution is deferred. */
import { test, expect } from '../frontend/node_modules/@playwright/test';

for (const role of ['admin', 'auditor'] as const) {
  test(`${role} reads live audit events and exports without user-admin access for auditors`, async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    page.on('requestfailed', request => errors.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`));
    const password = role === 'admin' ? process.env.E2E_ADMIN_PASSWORD : process.env.E2E_AUDITOR_PASSWORD;
    expect(password, `Set E2E_${role.toUpperCase()}_PASSWORD`).toBeTruthy();
    await page.goto('/login');
    await page.getByLabel('Email').fill(`${role}@ketsip.local`);
    await page.getByLabel('Password', { exact: true }).fill(password!);
    const login = page.waitForResponse(response => response.url().endsWith('/api/auth/login') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    const loginResponse = await login;
    expect(loginResponse.status()).toBe(200);
    const session = await loginResponse.json();
    await page.getByRole('link', { name: 'My Profile' }).click();
    const preference = session.user.defaultLandingPage === 'applications' ? 'Applications' : 'Executive dashboard';
    await page.getByRole('radio', { name: preference }).check();
    const saved = page.waitForResponse(response => response.url().endsWith('/api/auth/profile') && response.request().method() === 'PUT');
    await page.getByRole('button', { name: 'Save preference' }).click();
    expect((await saved).status()).toBe(200);
    await expect(page.getByText('Landing preference saved.')).toBeVisible();
    if (role === 'auditor') {
      await expect(page.getByRole('link', { name: 'Administration' })).toHaveCount(0);
      const users = await page.request.get('/api/users', { headers: { Authorization: `Bearer ${session.token}` } });
      const roles = await page.request.get('/api/roles', { headers: { Authorization: `Bearer ${session.token}` } });
      expect(users.status()).toBe(403);
      expect(roles.status()).toBe(403);
    }
    const listing = page.waitForResponse(response => response.url().includes('/api/audit-logs') && response.request().method() === 'GET');
    await page.getByRole('link', { name: 'Audit', exact: true }).click();
    const result = await listing;
    expect(result.status()).toBe(200);
    const data = await result.json();
    expect(data.items.length).toBeGreaterThan(0);
    await expect(page.getByText(data.items[0].details).first()).toBeVisible();
    expect(data.items.some((entry: { userId: string; details: string }) =>
      entry.userId === session.user.id && entry.details === 'Landing preference updated')).toBe(true);
    await page.getByLabel('User ID').fill(session.user.id);
    await page.getByLabel('Action').selectOption('login');
    const filtered = page.waitForResponse(response => response.url().includes('action=login') && response.url().includes('/api/audit-logs'));
    await page.getByRole('button', { name: 'Apply filters' }).click();
    const filteredResponse = await filtered;
    expect(filteredResponse.status()).toBe(200);
    expect((await filteredResponse.json()).items.some((entry: { userId: string }) => entry.userId === session.user.id)).toBe(true);
    const csv = page.waitForResponse(response => response.url().includes('format=csv'));
    const download = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export CSV' }).click();
    expect((await csv).status()).toBe(200);
    expect((await download).suggestedFilename()).toBe('audit-logs.csv');
    expect(errors).toEqual([]);
  });
}
