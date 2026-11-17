/** Provide live login and browser-error assertions without mocked routes. */
import { expect, type Page } from '../frontend/node_modules/@playwright/test';
import { loadEnv } from '../frontend/node_modules/vite';
import path from 'node:path';
const env = { ...loadEnv('development', path.resolve(import.meta.dirname, '../frontend'), ''), ...process.env };
export const credentials = {
  email: env.E2E_EMAIL || 'executive@ketsip.local',
  password: env.E2E_PASSWORD || 'ChangeDemo123!',
};
/** Capture browser failures before navigation, excluding only expected negative HTTP statuses. */
export function captureErrors(page: Page, expectedHttpFailure = false): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') {
      if (expectedHttpFailure && /^Failed to load resource: the server responded with a status of 401/.test(message.text())) return;
      errors.push(message.text());
    }
  });
  return errors;
}
/** Sign in from the visible login form and return the actual API identity. */
export async function login(page: Page) {
  await page.getByLabel('Email').fill(credentials.email);
  await page.getByLabel('Password', { exact: true }).fill(credentials.password);
  const response = page.waitForResponse((response) => response.url().endsWith('/api/auth/login') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  const result = await response;
  expect(result.status()).toBe(200);
  return await result.json() as { token: string; user: { name: string; email: string; role: string } };
}
