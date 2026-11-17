/** Exercise live report tables, downloads, scope and role restrictions; run later. */
import { test, expect } from '../frontend/node_modules/@playwright/test';

for (const role of ['executive', 'readonly'] as const) {
  test(`${role} views scoped reports and export permissions`, async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    page.on('requestfailed', request => errors.push(`${request.url()}: ${request.failure()?.errorText}`));
    const password = role === 'executive' ? process.env.E2E_EXECUTIVE_PASSWORD : process.env.E2E_READONLY_PASSWORD;
    expect(password).toBeTruthy();
    await page.goto('/login');
    await page.getByLabel('Email').fill(`${role}@ketsip.local`);
    await page.getByLabel('Password', { exact: true }).fill(password!);
    const login = page.waitForResponse(response => response.url().endsWith('/api/auth/login') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    const sessionResponse = await login;
    expect(sessionResponse.status()).toBe(200);
    const session = await sessionResponse.json();
    const apps = page.waitForResponse(response => response.url().includes('/api/reports/applications') && !response.url().includes('format=csv'));
    await page.getByRole('link', { name: 'Reports', exact: true }).click();
    const appResponse = await apps;
    expect(appResponse.status()).toBe(200);
    const appData = await appResponse.json();
    expect(appData.items.length).toBeGreaterThan(0);
    if (role === 'readonly') {
      expect(appData.items.every((item: { portfolioId: string }) => session.user.portfolioAccess.includes(item.portfolioId))).toBe(true);
    }
    await expect(page.getByRole('link', { name: appData.items[0].name, exact: true })).toBeVisible();
    if (role === 'executive') {
      const csv = page.waitForResponse(response => response.url().includes('/api/reports/applications') && response.url().includes('format=csv'));
      const download = page.waitForEvent('download');
      await page.getByRole('button', { name: 'Export CSV' }).click();
      expect((await csv).status()).toBe(200);
      expect((await download).suggestedFilename()).toBe('applications.csv');
    } else {
      await expect(page.getByRole('button', { name: 'Export CSV' })).toHaveCount(0);
      const denied = await page.request.get('/api/reports/applications?format=csv', { headers: { Authorization: `Bearer ${session.token}` } });
      expect(denied.status()).toBe(403);
    }
    const portfolioResponsePromise = page.waitForResponse(response => response.url().includes('/api/reports/portfolios') && !response.url().includes('format=csv'));
    await page.getByRole('link', { name: 'Portfolio Report' }).click();
    const portfolioResponse = await portfolioResponsePromise;
    expect(portfolioResponse.status()).toBe(200);
    const data = await portfolioResponse.json();
    expect(data.items.length).toBeGreaterThan(0);
    await expect(page.getByRole('link', { name: data.items[0].name, exact: true })).toBeVisible();
    if (role === 'executive') {
      const csv = page.waitForResponse(response => response.url().includes('/api/reports/portfolios') && response.url().includes('format=csv'));
      const download = page.waitForEvent('download');
      await page.getByRole('button', { name: 'Export CSV' }).click();
      expect((await csv).status()).toBe(200);
      expect((await download).suggestedFilename()).toBe('portfolios.csv');
    } else {
      const denied = await page.request.get('/api/reports/portfolios?format=csv', { headers: { Authorization: `Bearer ${session.token}` } });
      expect(denied.status()).toBe(403);
    }
    expect(errors).toEqual([]);
  });
}
