/** Exercise live report tables, downloads, scope and role restrictions; run later. */
import { test, expect, type Download, type Response } from '../frontend/node_modules/@playwright/test/index.mjs';
import { readFile } from 'node:fs/promises';

/** Verify the browser downloaded the live response, including a real inventory row. */
async function verifyCsv(response: Response, download: Download, filename: string, fields: unknown[]) {
  expect(response.status()).toBe(200);
  expect(download.suggestedFilename()).toBe(filename);
  const path = await download.path();
  expect(path).toBeTruthy();
  const content = await readFile(path!, 'utf8');
  expect(content).toBe(await response.text());
  const cell = (value: unknown) => {
    let text = value == null ? '' : String(value);
    const leading = text.replace(/^ +/, '');
    if (/^[=+\-@]/.test(leading) || /^[\x00-\x1f\x7f]/.test(leading)) text = `'${text}`;
    return `"${text.replace(/"/g, '""')}"`;
  };
  expect(content).toContain(fields.map(cell).join(','));
}

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
    // The inventory export is a separate entry point from the report export.
    const inventory = page.waitForResponse(response => response.url().includes('/api/applications') && !response.url().includes('/reports/'));
    await page.getByRole('link', { name: 'Applications', exact: true }).click();
    expect((await inventory).status()).toBe(200);
    await page.getByLabel('Search applications').fill(appData.items[0].name);
    const filtered = page.waitForResponse(response => response.url().includes('/api/applications?') && new URL(response.url()).searchParams.get('search') === appData.items[0].name);
    await page.getByRole('button', { name: 'Apply filters' }).click();
    const filteredResponse = await filtered;
    expect(filteredResponse.status()).toBe(200);
    const filteredData = await filteredResponse.json();
    expect(filteredData.items.length).toBeGreaterThan(0);
    const row = filteredData.items.find((item: { id: string }) => item.id === appData.items[0].id);
    expect(row).toBeTruthy();
    await expect(page.getByRole('link', { name: row.name, exact: true })).toBeVisible();
    if (role === 'executive') {
      const csv = page.waitForResponse(response => response.url().includes('/api/reports/applications?') && new URL(response.url()).searchParams.get('format') === 'csv');
      const download = page.waitForEvent('download');
      await page.getByRole('button', { name: 'Export CSV' }).click();
      const csvResponse = await csv;
      expect(new URL(csvResponse.url()).searchParams.get('search')).toBe(row.name);
      await verifyCsv(csvResponse, await download, 'applications.csv', [row.name, row.portfolioName, row.criticality, row.tier, row.lifecycleStatus, row.applicationHealthScore, row.automationCoverage, row.openCriticalDefects, row.riskLevel]);
    } else {
      await expect(page.getByRole('button', { name: 'Export CSV' })).toHaveCount(0);
      const denied = await page.request.get(`/api/reports/applications?format=csv&search=${encodeURIComponent(row.name)}`, { headers: { Authorization: `Bearer ${session.token}` } });
      expect(denied.status()).toBe(403);
    }
    const reportAgain = page.waitForResponse(response => response.url().includes('/api/reports/applications') && !response.url().includes('format=csv'));
    await page.getByRole('link', { name: 'Reports', exact: true }).click();
    expect((await reportAgain).status()).toBe(200);
    if (role === 'executive') {
      const csv = page.waitForResponse(response => response.url().includes('/api/reports/applications') && response.url().includes('format=csv'));
      const download = page.waitForEvent('download');
      await page.getByRole('button', { name: 'Export CSV' }).click();
      const item = appData.items[0];
      await verifyCsv(await csv, await download, 'applications.csv', [item.name, item.portfolioName, item.criticality, item.tier, item.lifecycleStatus, item.applicationHealthScore, item.automationCoverage, item.openCriticalDefects, item.riskLevel]);
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
      const item = data.items[0];
      await verifyCsv(await csv, await download, 'portfolios.csv', [item.name, item.owner, item.productArea, item.applicationCount, item.qualityScore, item.status]);
    } else {
      await expect(page.getByRole('button', { name: 'Export CSV' })).toHaveCount(0);
      const denied = await page.request.get('/api/reports/portfolios?format=csv', { headers: { Authorization: `Bearer ${session.token}` } });
      expect(denied.status()).toBe(403);
    }
    expect(errors).toEqual([]);
  });
}
