/** Exercise real role editing and restoration; execution is deferred. */
import { test, expect } from '../frontend/node_modules/@playwright/test';

test('administrator edits and restores a role', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('requestfailed', request => errors.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`));
  const password = process.env.E2E_ADMIN_PASSWORD;
  expect(password, 'Set E2E_ADMIN_PASSWORD to a rotated administrator password').toBeTruthy();
  await page.goto('/login');
  await page.getByLabel('Email').fill('admin@ketsip.local');
  await page.getByLabel('Password', { exact: true }).fill(password!);
  const login = page.waitForResponse(r => r.url().endsWith('/api/auth/login') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  const loginResponse = await login;
  expect(loginResponse.status()).toBe(200);
  const session = await loginResponse.json();
  await page.getByRole('link', { name: 'Administration' }).click();
  const listing = page.waitForResponse(r => r.url().includes('/api/roles?') && r.request().method() === 'GET');
  await page.getByRole('link', { name: 'Roles', exact: true }).click();
  const rolesResponse = await listing;
  expect(rolesResponse.status()).toBe(200);
  const roles = await rolesResponse.json();
  const role = roles.items.find((item: { name: string }) => item.name === 'Engineer');
  expect(role).toBeTruthy();
  try {
    await page.getByRole('button', { name: `Edit ${role.name}` }).click();
    await expect(page.getByLabel('Description')).toHaveValue(role.description);
    const checkbox = page.getByLabel('edit', { exact: true });
    const wasChecked = await checkbox.isChecked();
    await checkbox.setChecked(!wasChecked);
    const saved = page.waitForResponse(r => r.url().endsWith(`/api/roles/${role.id}`) && r.request().method() === 'PUT');
    await page.getByRole('button', { name: 'Save role' }).click();
    const result = await saved;
    expect(result.status()).toBe(200);
    expect((await result.json()).permissions.includes('edit')).toBe(!wasChecked);
    await expect(page.getByText('Role saved.')).toBeVisible();
    await page.reload();
    await page.getByRole('button', { name: 'Edit Engineer' }).click();
    await expect(checkbox).toBeChecked({ checked: !wasChecked });
    expect(errors).toEqual([]);
  } finally {
    const restored = await page.request.put(`/api/roles/${role.id}`, {
      headers: { Authorization: `Bearer ${session.token}` },
      data: { description: role.description, permissions: role.permissions },
    });
    expect(restored.status()).toBe(200);
  }
});
