/** Verify account list, validation, mutations and permission states. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../../App';
import { TOKEN_KEY } from '../../shared/api';
import type { User } from '../../types';

const id = '507f1f77bcf86cd799439011';
const identity: User = {
  id, name: 'Admin', email: 'admin@ketsip.local', role: 'Administrator',
  permissions: ['view', 'administer'], portfolioAccess: [], status: 'Active', lastLogin: null,
  authSource: 'local', managerName: null, vendorIndicator: false, defaultLandingPage: null,
  mustChangePassword: false, createdAt: '2025-01-01T00:00:00Z', updatedAt: '2025-01-01T00:00:00Z',
};
const item: User = { ...identity, id: '507f1f77bcf86cd799439012', name: 'Example User', email: 'example@ketsip.local', role: 'Engineer' };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const page = (items: unknown[]) => ({ items, total: items.length, page: 1, pageSize: 25 });
/** Mount the real routes and mock only the HTTP boundary. */
function mount(user = identity) {
  localStorage.setItem(TOKEN_KEY, 'test-token');
  window.history.replaceState(null, '', '/administration');
  const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith('/auth/me')) return json(user);
    if (url.includes('/portfolios')) return json(page([]));
    if (url.includes('/users') && init?.method === 'POST') return json(item, 201);
    if (url.includes('/users')) return json(page([item]));
    return json({ detail: 'Unexpected request' }, 500);
  });
  render(<App />);
  return fetch;
}
beforeEach(() => localStorage.clear());

describe('User administration', () => {
  it('renders users and submits URL-backed search', async () => {
    const fetch = mount();
    expect(await screen.findByText('example@ketsip.local')).toBeVisible();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Search users'), 'Example');
    await user.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(window.location.search).toContain('search=Example'));
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/users?search=Example'))).toBe(true);
  });

  it('validates missing fields and displays conflicts without losing input', async () => {
    const fetch = mount();
    await screen.findByText('example@ketsip.local');
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Create user' }));
    await screen.findByRole('form', { name: 'User form' });
    await user.click(screen.getByRole('button', { name: 'Save user' }));
    expect(screen.getByText('Password must contain 12–72 UTF-8 bytes.')).toBeVisible();
    await user.type(screen.getByLabelText('Name'), 'Example User');
    await user.type(screen.getByLabelText('Email'), 'example@ketsip.local');
    await user.type(screen.getByLabelText('Password', { exact: true }), 'NewPassword123!');
    fetch.mockImplementation(async (input, init) => init?.method === 'POST'
      ? json({ detail: 'Email already exists' }, 409)
      : String(input).endsWith('/auth/me') ? json(identity) : json(page([])));
    await user.click(screen.getByRole('button', { name: 'Save user' }));
    expect(await screen.findByText('Email already exists')).toBeVisible();
    expect(screen.getByLabelText('Name')).toHaveValue('Example User');
  });

  it('saves a new account and shows success', async () => {
    const fetch = mount();
    await screen.findByText('example@ketsip.local');
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Create user' }));
    await screen.findByRole('form', { name: 'User form' });
    await user.type(screen.getByLabelText('Name'), 'New User');
    await user.type(screen.getByLabelText('Email'), 'new@ketsip.local');
    await user.type(screen.getByLabelText('Password', { exact: true }), 'NewPassword123!');
    await user.click(screen.getByRole('button', { name: 'Save user' }));
    expect(await screen.findByText('User created.')).toBeVisible();
    const request = fetch.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(JSON.parse(String(request?.[1]?.body)).email).toBe('new@ketsip.local');
  });

  it('denies non-admins and shows a retry on list failure', async () => {
    const fetch = mount({ ...identity, role: 'Auditor' });
    expect(await screen.findByText('Access denied')).toBeVisible();
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/users?'))).toBe(false);
  });

  it('allows retry after the users list fails', async () => {
    const fetch = mount();
    fetch.mockImplementation(async input => String(input).endsWith('/auth/me') ? json(identity) : json({ detail: 'Unavailable' }, 503));
    expect(await screen.findByText('Unavailable')).toBeVisible();
    fetch.mockImplementation(async input => String(input).endsWith('/auth/me') ? json(identity) : json(page([item])));
    await userEvent.setup().click(screen.getByRole('button', { name: 'Retry users' }));
    expect(await screen.findByText('example@ketsip.local')).toBeVisible();
  });
});
