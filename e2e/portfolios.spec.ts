/** Exercise real portfolio journeys against the running browser and API; no routes are mocked. */
import { test, expect, type Page } from '../frontend/node_modules/@playwright/test/index.mjs';
const adminPassword = process.env.E2E_ADMIN_PASSWORD;
const demoPassword = process.env.E2E_DEMO_PASSWORD;

/** Sign in with an already-rotated Administrator or a seeded scoped user. */
async function signIn(page: Page, email: string, password: string) {
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  const response = page.waitForResponse(r => r.url().endsWith('/api/auth/login') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  const result = await response;
  expect(result.status()).toBe(200);
  return await result.json() as { token: string; user: { mustChangePassword: boolean } };
}

/** Capture unexpected browser errors while allowing the deliberately tested 409. */
function watch(page: Page) {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error' && !/^Failed to load resource: the server responded with a status of 409/.test(message.text())) errors.push(message.text());
  });
  page.on('requestfailed', request => errors.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`));
  return errors;
}

test('administrator creates, edits, reloads, filters and deletes an unlinked portfolio', async ({ page }) => {
  const errors = watch(page);
  expect(adminPassword, 'Set E2E_ADMIN_PASSWORD to an Administrator password already changed from the seed.').toBeTruthy();
  await page.goto('/login');
  const login = await signIn(page, 'admin@ketsip.local', adminPassword!);
  expect(login.user.mustChangePassword).toBe(false);
  const name = `Portfolio journey ${Date.now()}-${test.info().project.name}`;
  let identifier = '';
  try {
    await page.getByRole('link', { name: 'Portfolios', exact: true }).click();
    await page.getByRole('button', { name: 'Create portfolio' }).click();
    await page.getByRole('button', { name: 'Save portfolio' }).click();
    await expect(page.getByText('Name is required.')).toBeVisible();
    await page.getByLabel('Name', { exact: true }).fill(name);
    await page.getByLabel('Owner', { exact: true }).fill('Journey owner');
    await page.getByLabel('Product area', { exact: true }).fill('Journey area');
    const created = page.waitForResponse(r => r.url().endsWith('/api/portfolios') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Save portfolio' }).click();
    const createResponse = await created;
    expect(createResponse.status()).toBe(201);
    const body = await createResponse.json();
    identifier = body.id;
    expect(body.name).toBe(name);
    await expect(page.getByRole('heading', { name })).toBeVisible();
    await expect(page.getByText('Journey owner')).toBeVisible();
    await expect(page.getByText('No linked applications.', { exact: true })).toBeVisible();
    const empty = await page.request.get(`/api/portfolios/${identifier}/applications`, { headers: { Authorization: `Bearer ${login.token}` } });
    expect(empty.status()).toBe(200);
    expect((await empty.json()).total).toBe(0);
    await page.getByRole('button', { name: 'Edit portfolio' }).click();
    await page.getByLabel('Owner', { exact: true }).fill('Updated owner');
    const updated = page.waitForResponse(r => r.url().endsWith(`/api/portfolios/${identifier}`) && r.request().method() === 'PUT');
    await page.getByRole('button', { name: 'Save portfolio' }).click();
    expect((await updated).status()).toBe(200);
    await expect(page.getByText('Updated owner')).toBeVisible();
    await page.reload();
    await expect(page.getByText('Updated owner')).toBeVisible();
    await page.getByRole('link', { name: 'Back to portfolios' }).click();
    await page.getByLabel('Search portfolios').fill(name);
    await page.getByRole('button', { name: 'Apply filters' }).click();
    await page.getByRole('link', { name, exact: true }).click();
    await page.getByRole('button', { name: 'Delete portfolio' }).click();
    const deleted = page.waitForResponse(r => r.url().endsWith(`/api/portfolios/${identifier}`) && r.request().method() === 'DELETE');
    await page.getByRole('button', { name: 'Confirm delete' }).click();
    expect((await deleted).status()).toBe(204);
    identifier = '';
    await expect(page.getByText('Portfolio deleted.')).toBeVisible();
    expect(errors).toEqual([]);
  } finally {
    if (identifier) {
      const cleanup = await page.request.delete(`/api/portfolios/${identifier}`, { headers: { Authorization: `Bearer ${login.token}` } });
      expect(cleanup.status(), 'Failed to clean up the portfolio created by this journey').toBe(204);
    }
  }
});

test('linked deletion conflicts and read-only users cannot mutate', async ({ page }) => {
  const errors = watch(page);
  expect(adminPassword, 'Set E2E_ADMIN_PASSWORD to an Administrator password already changed from the seed.').toBeTruthy();
  expect(demoPassword, 'Set E2E_DEMO_PASSWORD.').toBeTruthy();
  await page.goto('/login');
  const admin = await signIn(page, 'admin@ketsip.local', adminPassword!);
  expect(admin.user.mustChangePassword).toBe(false);
  const listing = await page.request.get('/api/portfolios?pageSize=100', { headers: { Authorization: `Bearer ${admin.token}` } });
  expect(listing.status()).toBe(200);
  const portfolios = (await listing.json()).items as { id: string; name: string; applicationCount: number }[];
  const linked = portfolios.find(item => item.applicationCount > 0);
  expect(linked, 'Preload at least one real linked application in the E2E database; this slice does not create applications.').toBeTruthy();
  await page.getByRole('link', { name: 'Portfolios', exact: true }).click();
  await page.getByLabel('Search portfolios').fill(linked!.name);
  await page.getByRole('button', { name: 'Apply filters' }).click();
  await page.getByRole('link', { name: linked!.name, exact: true }).click();
  const linkedResponse = await page.request.get(`/api/portfolios/${linked!.id}/applications`, { headers: { Authorization: `Bearer ${admin.token}` } });
  expect(linkedResponse.status()).toBe(200);
  const applications = await linkedResponse.json();
  expect(applications.total).toBeGreaterThan(0);
  await expect(page.getByText(applications.items[0].name, { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Delete portfolio' }).click();
  const conflict = page.waitForResponse(r => r.url().endsWith(`/api/portfolios/${linked!.id}`) && r.request().method() === 'DELETE');
  await page.getByRole('button', { name: 'Confirm delete' }).click();
  expect((await conflict).status()).toBe(409);
  await expect(page.getByRole('alert')).toContainText('linked applications');
  await page.getByRole('button', { name: 'Cancel' }).click();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await signIn(page, 'readonly@ketsip.local', demoPassword!);
  await page.getByRole('link', { name: 'Portfolios', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Create portfolio' })).toHaveCount(0);
  const list = await page.request.get('/api/portfolios', { headers: { Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem('etsip.token'))}` } });
  const visible = (await list.json()).items as { id: string; name: string }[];
  expect(visible.length).toBeGreaterThan(0);
  await page.getByRole('link', { name: visible[0].name, exact: true }).click();
  await expect(page.getByRole('button', { name: 'Edit portfolio' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Delete portfolio' })).toHaveCount(0);
  expect(errors).toEqual([]);
});
