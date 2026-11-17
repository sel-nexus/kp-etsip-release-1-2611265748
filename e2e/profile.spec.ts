/** Specify live profile journeys; the parent runs them after independent review. */
import { test, expect, type Page } from '../frontend/node_modules/@playwright/test';
import { loadEnv } from '../frontend/node_modules/vite';
import path from 'node:path';
import { captureErrors, credentials, login } from './helpers';

const backendEnv = { ...loadEnv('development', path.resolve(import.meta.dirname, '../backend'), ''), ...process.env };
const profileEmail = process.env.E2E_PROFILE_EMAIL || 'engineer@ketsip.local';
const profilePassword = process.env.E2E_PROFILE_PASSWORD || backendEnv.SEED_DEMO_PASSWORD || credentials.password;
const adminPassword = process.env.E2E_ADMIN_PASSWORD || backendEnv.SEED_ADMIN_PASSWORD;

/** Sign in with chosen credentials through the real visible form. */
async function signIn(page: Page, email: string, password: string, status = 200) {
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  const pending = page.waitForResponse((response) => response.url().endsWith('/api/auth/login') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  const response = await pending;
  expect(response.status()).toBe(status);
  return response.json();
}

/** Rotate passwords through visible inputs and await the real revoking response. */
async function rotate(page: Page, current: string, next: string) {
  await page.getByLabel('Current password', { exact: true }).fill(current);
  await page.getByLabel('New password', { exact: true }).fill(next);
  await page.getByLabel('Confirm new password', { exact: true }).fill(next);
  const pending = page.waitForResponse((response) => response.url().endsWith('/api/auth/change-password'));
  await page.getByRole('button', { name: 'Change password', exact: true }).click();
  expect((await pending).status()).toBe(204);
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  await expect(page.getByText('Password changed. Sign in again with your new password.')).toBeVisible();
}

test('account → profile → save preference → reload → persisted preference', async ({ page }, testInfo) => {
  const errors = captureErrors(page);
  await page.goto('/');
  await page.getByRole('link', { name: 'Sign in', exact: true }).click();
  const result = await login(page);
  await page.getByRole('link', { name: 'My Profile', exact: true }).click();
  await expect(page.getByText(result.user.email, { exact: true })).toBeVisible();
  await page.getByRole('radio', { name: 'Applications', exact: true }).check();
  const save = page.waitForResponse((response) => response.url().endsWith('/api/auth/profile'));
  await page.getByRole('button', { name: 'Save preference' }).click();
  const saved = await save;
  expect(saved.status()).toBe(200);
  expect((await saved.json()).defaultLandingPage).toBe('applications');
  await expect(page.getByText('Landing preference saved.')).toBeVisible();
  const me = page.waitForResponse((response) => response.url().endsWith('/api/auth/me'));
  await page.reload();
  const restored = await me;
  expect(restored.status()).toBe(200);
  expect((await restored.json()).defaultLandingPage).toBe('applications');
  await expect(page.getByRole('radio', { name: 'Applications', exact: true })).toBeChecked();
  await page.screenshot({ path: testInfo.outputPath('profile.png'), fullPage: true });
  await page.getByRole('link', { name: 'Account & session', exact: true }).click();
  await page.getByRole('link', { name: 'Manage profile and password' }).click();
  await expect(page.getByRole('radio', { name: 'Applications', exact: true })).toBeChecked();
  expect(errors).toEqual([]);
});

test('change password → old login denied → new login succeeds → restore account password', async ({ page }) => {
  const errors = captureErrors(page, true);
  await page.goto('/login');
  const result = await signIn(page, profileEmail, profilePassword);
  await page.getByRole('link', { name: 'My Profile', exact: true }).click();
  await expect(page.getByText(result.user.email, { exact: true })).toBeVisible();
  await page.getByLabel('Current password', { exact: true }).fill(profilePassword);
  await page.getByLabel('New password', { exact: true }).fill('short');
  await page.getByLabel('Confirm new password', { exact: true }).fill('short');
  await page.getByRole('button', { name: 'Change password', exact: true }).click();
  await expect(page.getByText('New password must contain 12–72 UTF-8 bytes.')).toBeVisible();
  const replacement = `ProfileJourney-${Date.now()}!`;
  await rotate(page, profilePassword, replacement);
  expect(await page.evaluate(() => localStorage.getItem('etsip.token'))).toBeNull();
  await signIn(page, profileEmail, profilePassword, 401);
  await expect(page.getByRole('alert')).toHaveText('Invalid email or password');
  const fresh = await signIn(page, profileEmail, replacement);
  expect(fresh.user.mustChangePassword).toBe(false);
  await expect(page.getByRole('heading', { name: 'Account & session' })).toBeVisible();
  await page.getByRole('link', { name: 'My Profile', exact: true }).click();
  await rotate(page, replacement, profilePassword);
  await signIn(page, profileEmail, profilePassword);
  await expect(page.getByText(result.user.email, { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test('seed administrator is forced to profile before account access', async ({ page }) => {
  const errors = captureErrors(page);
  expect(adminPassword, 'Configure E2E_ADMIN_PASSWORD or SEED_ADMIN_PASSWORD for the untouched seed administrator').toBeTruthy();
  await page.goto('/account');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  const result = await signIn(page, 'admin@ketsip.local', adminPassword!);
  expect(result.user.mustChangePassword).toBe(true);
  await expect(page.getByRole('heading', { name: 'My Profile' })).toBeVisible();
  await expect(page.getByText(/Password change is required before business access/)).toBeVisible();
  await expect(page.getByRole('link', { name: 'Account & session' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Change password', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  expect(errors).toEqual([]);
});
