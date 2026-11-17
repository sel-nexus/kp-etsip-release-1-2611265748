/** Provide live login and browser-error assertions without mocked routes. */
import { expect, type Page, type TestInfo } from '../frontend/node_modules/@playwright/test/index.mjs';
import { randomUUID } from 'node:crypto';
import { e2eApiUrl, forcePasswordChange } from '../frontend/scripts/e2e-setup';
export const credentials = {
  email: 'executive@ketsip.local',
  password: process.env.E2E_DEMO_PASSWORD!,
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
  return await result.json() as { token: string; user: { name: string; email: string; role: string; permissions: string[]; defaultLandingPage: 'dashboard' | 'applications' | null; mustChangePassword: boolean } };
}

/** Create and deactivate a unique account through the real backend, even on test failure. */
export async function withDisposableUser(
  page: Page, testInfo: TestInfo, role: 'Engineer' | 'Administrator' | 'Executive', forced: boolean,
  journey: (user: { email: string; password: string; id: string }) => Promise<void>,
) {
  const adminPassword = process.env.E2E_ADMIN_PASSWORD;
  expect(adminPassword, 'Set E2E_ADMIN_PASSWORD to the rotated E2E business administrator password').toBeTruthy();
  const api = page.request;
  const loginResponse = await api.post(`${e2eApiUrl}/api/auth/login`, {
    data: { email: 'admin@ketsip.local', password: adminPassword },
  });
  expect(loginResponse.status()).toBe(200);
  const admin = await loginResponse.json();
  expect(admin.user).toMatchObject({ role: 'Administrator', mustChangePassword: false });
  const headers = { Authorization: `Bearer ${admin.token}` };
  let portfolioAccess: string[] = [];
  if (role === 'Engineer') {
    const response = await api.get(`${e2eApiUrl}/api/portfolios?pageSize=100`, { headers });
    expect(response.status()).toBe(200);
    const portfolios = (await response.json()).items as { id: string }[];
    expect(portfolios.length).toBeGreaterThan(0);
    portfolioAccess = [portfolios[0].id];
  }
  const project = testInfo.project.name.toLowerCase().replace(/[^a-z0-9]+/g, '-');
  const unique = `${project}-${randomUUID()}`;
  const email = `e2e-${unique}@example.com`;
  const password = `Journey-${randomUUID()}!`;
  const created = await api.post(`${e2eApiUrl}/api/users`, {
    headers, data: { name: `E2E ${role} ${unique}`, email, password, role, portfolioAccess },
  });
  expect(created.status()).toBe(201);
  const account = await created.json() as { id: string; email: string; role: string; mustChangePassword: boolean };
  try {
    expect(account).toMatchObject({ email, role, mustChangePassword: false });
    if (forced) {
      expect(role).toBe('Administrator');
      await forcePasswordChange(account.id, email);
      const persisted = await api.get(`${e2eApiUrl}/api/users/${account.id}`, { headers });
      expect(persisted.status()).toBe(200);
      expect(await persisted.json()).toMatchObject({ id: account.id, email, role, mustChangePassword: true });
      const forcedLogin = await api.post(`${e2eApiUrl}/api/auth/login`, { data: { email, password } });
      expect(forcedLogin.status()).toBe(200);
      const forcedSession = await forcedLogin.json();
      expect(forcedSession.user).toMatchObject({ id: account.id, role, mustChangePassword: true });
      const denied = await api.get(`${e2eApiUrl}/api/users`, { headers: { Authorization: `Bearer ${forcedSession.token}` } });
      expect(denied.status()).toBe(403);
    }
    await journey({ id: account.id, email, password });
  } finally {
    const deactivated = await api.delete(`${e2eApiUrl}/api/users/${account.id}`, { headers });
    expect(deactivated.status(), `Deactivate disposable ${email}`).toBe(204);
    const check = await api.get(`${e2eApiUrl}/api/users/${account.id}`, { headers });
    expect(check.status()).toBe(200);
    expect(await check.json()).toMatchObject({ id: account.id, email, status: 'Inactive' });
  }
}
