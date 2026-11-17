/** Exercise only live local identity journeys; do not run during slice implementation. */
import { test, expect } from '../frontend/node_modules/@playwright/test/index.mjs';
import { captureErrors, login } from './helpers';

test('entry → real login → account navigation → restored session → revoked logout', async ({ page }, testInfo) => {
  const errors = captureErrors(page);
  await page.goto('/');
  await page.getByRole('link', { name: 'Sign in', exact: true }).click();
  const result = await login(page);
  expect(result.user.role).toBe('Executive');
  expect(result.user.mustChangePassword).toBe(false);
  expect([null, 'dashboard']).toContain(result.user.defaultLandingPage);
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole('heading', { name: 'Executive dashboard' })).toBeVisible();
  await page.getByRole('link', { name: 'Account & session', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Account & session' })).toBeVisible();
  await expect(page.getByText(result.user.email, { exact: true })).toBeVisible();
  const role = page.getByRole('region', { name: 'Current identity' }).locator('dt').filter({ hasText: /^Role$/ }).locator('xpath=following-sibling::dd[1]');
  await expect(role).toBeVisible();
  await expect(role).toHaveText(result.user.role);
  await page.getByRole('link', { name: 'KP ETSIP', exact: true }).click();
  await page.getByRole('link', { name: 'Continue' }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.getByRole('link', { name: 'Account & session', exact: true }).click();
  const me = page.waitForResponse((response) => response.url().endsWith('/api/auth/me'));
  await page.reload();
  expect((await me).status()).toBe(200);
  await expect(page.getByText(result.user.email, { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('account.png'), fullPage: true });
  const logout = page.waitForResponse((response) => response.url().endsWith('/api/auth/logout'));
  await page.getByRole('button', { name: 'Sign out' }).click();
  expect((await logout).status()).toBe(204);
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('etsip.token'))).toBeNull();
  expect(errors).toEqual([]);
});

test('invalid credentials show a generic error without protected navigation', async ({ page }) => {
  const errors = captureErrors(page, true);
  await page.goto('/login');
  await page.getByLabel('Email').fill('unknown@ketsip.local');
  await page.getByLabel('Password', { exact: true }).fill('WrongPassword123!');
  const response = page.waitForResponse((response) => response.url().endsWith('/api/auth/login'));
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  expect((await response).status()).toBe(401);
  await expect(page.getByRole('alert')).toHaveText('Invalid email or password');
  await expect(page).toHaveURL(/\/login$/);
  expect(errors).toEqual([]);
});

test('direct protected initial entry requires real authentication', async ({ page }) => {
  const errors = captureErrors(page);
  await page.goto('/account');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
  const result = await login(page);
  expect(result.user.role).toBe('Executive');
  expect([null, 'dashboard']).toContain(result.user.defaultLandingPage);
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole('heading', { name: 'Executive dashboard' })).toBeVisible();
  await page.getByRole('link', { name: 'Account & session', exact: true }).click();
  await expect(page.getByText(result.user.email, { exact: true })).toBeVisible();
  const role = page.getByRole('region', { name: 'Current identity' }).locator('dt').filter({ hasText: /^Role$/ }).locator('xpath=following-sibling::dd[1]');
  await expect(role).toBeVisible();
  await expect(role).toHaveText(result.user.role);
  expect(errors).toEqual([]);
});
