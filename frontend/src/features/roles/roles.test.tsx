/** Exercise the visible role editor and its permission boundary. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../../App';
import { TOKEN_KEY } from '../../shared/api';
import type { User } from '../../types';

const identity: User = {
  id: '507f1f77bcf86cd799439011', name: 'Admin', email: 'admin@ketsip.local', role: 'Administrator',
  permissions: ['view', 'administer'], portfolioAccess: [], status: 'Active', lastLogin: null,
  authSource: 'local', managerName: null, vendorIndicator: false, defaultLandingPage: null,
  mustChangePassword: false, createdAt: '2025-01-01T00:00:00Z', updatedAt: '2025-01-01T00:00:00Z',
};
const role = { id: '507f1f77bcf86cd799439012', name: 'Engineer', description: 'Engineering', permissions: ['view'],
  createdAt: '2025-01-01T00:00:00Z', updatedAt: '2025-01-01T00:00:00Z' };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const page = { items: [role], total: 1, page: 1, pageSize: 100 };

/** Render real routing with the HTTP boundary replaced. */
function mount(user = identity, fail = false) {
  localStorage.setItem(TOKEN_KEY, 'token');
  window.history.replaceState(null, '', '/administration/roles');
  const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    if (String(input).endsWith('/auth/me')) return json(user);
    if (init?.method === 'PUT') return fail ? json({ detail: 'Conflict' }, 409) : json({ ...role, ...JSON.parse(String(init.body)) });
    return json(page);
  });
  render(<App />);
  return fetch;
}
beforeEach(() => localStorage.clear());

describe('Role administration', () => {
  it('edits and saves a selected role with visible feedback', async () => {
    const fetch = mount();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Edit Engineer' }));
    expect(screen.getAllByRole('checkbox')).toHaveLength(6);
    await user.clear(screen.getByLabelText('Description'));
    await user.type(screen.getByLabelText('Description'), 'Updated role');
    await user.click(screen.getByLabelText('edit'));
    await user.click(screen.getByRole('button', { name: 'Save role' }));
    expect(await screen.findByText('Role saved.')).toBeVisible();
    const request = fetch.mock.calls.find(([, init]) => init?.method === 'PUT');
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({ description: 'Updated role', permissions: ['view', 'edit'] });
  });

  it('shows a failed save without discarding the editor', async () => {
    mount(identity, true);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Edit Engineer' }));
    await user.click(screen.getByRole('button', { name: 'Save role' }));
    expect(await screen.findByText('Conflict')).toBeVisible();
    expect(screen.getByLabelText('Description')).toHaveValue('Engineering');
  });

  it('denies a non-administrator even with administer', async () => {
    const fetch = mount({ ...identity, role: 'Auditor' });
    expect(await screen.findByText('Access denied')).toBeVisible();
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/roles?'))).toBe(false);
  });
});
