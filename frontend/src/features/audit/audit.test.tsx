/** Exercise audit access, filters, failures and CSV download. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../../App';
import { TOKEN_KEY } from '../../shared/api';
import type { User } from '../../types';

const identity: User = {
  id: '507f1f77bcf86cd799439011', name: 'Auditor', email: 'auditor@ketsip.local', role: 'Auditor',
  permissions: ['view', 'export'], portfolioAccess: [], status: 'Active', lastLogin: null,
  authSource: 'local', managerName: null, vendorIndicator: false, defaultLandingPage: null,
  mustChangePassword: false, createdAt: '2025-01-01T00:00:00Z', updatedAt: '2025-01-01T00:00:00Z',
};
const record = { id: '507f1f77bcf86cd799439012', timestamp: '2025-01-01T00:00:00Z',
  userId: identity.id, userName: 'Auditor', action: 'login', entityType: 'user', entityId: identity.id,
  details: 'Login succeeded', createdAt: '2025-01-01T00:00:00Z', updatedAt: '2025-01-01T00:00:00Z' };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });

/** Render the actual route while replacing only the HTTP boundary. */
function mount(user = identity, fail = false) {
  localStorage.setItem(TOKEN_KEY, 'token');
  window.history.replaceState(null, '', '/audit');
  const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const url = String(input);
    if (url.endsWith('/auth/me')) return json(user);
    if (url.includes('format=csv')) return new Response('action\nlogin\n', { status: 200 });
    return fail ? json({ detail: 'Audit unavailable' }, 503) : json({ items: [record], total: 1, page: 1, pageSize: 25 });
  });
  render(<App />);
  return fetch;
}
beforeEach(() => localStorage.clear());

describe('Audit page', () => {
  it('renders records and applies URL-backed filters', async () => {
    const fetch = mount();
    const user = userEvent.setup();
    expect(await screen.findByText('Login succeeded')).toBeVisible();
    expect(screen.queryByRole('link', { name: 'Administration' })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText('User ID'), identity.id);
    await user.selectOptions(screen.getByLabelText('Action'), 'login');
    await user.type(screen.getByLabelText('From UTC'), '2025-01-01T00:00:00Z');
    await user.click(screen.getByRole('button', { name: 'Apply filters' }));
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).includes('action=login') && String(url).includes(`userId=${identity.id}`))).toBe(true));
    expect(window.location.search).toContain('from=');
  });

  it('shows errors and permits retry', async () => {
    mount(identity, true);
    expect(await screen.findByText('Audit unavailable')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Retry audit logs' })).toBeVisible();
  });

  it('displays loading and an empty result', async () => {
    localStorage.setItem(TOKEN_KEY, 'token');
    window.history.replaceState(null, '', '/audit');
    let resolvePage!: (value: Response) => void;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
      if (String(input).endsWith('/auth/me')) return json(identity);
      return new Promise<Response>(resolve => { resolvePage = resolve; });
    });
    render(<App />);
    expect(await screen.findByText('Loading audit logs…')).toBeVisible();
    resolvePage(json({ items: [], total: 0, page: 1, pageSize: 25 }));
    expect(await screen.findByText('No audit events.')).toBeVisible();
  });

  it('denies other roles and hides export without its live permission', async () => {
    const fetch = mount({ ...identity, role: 'Engineer', permissions: ['view', 'export'] });
    expect(await screen.findByText('Access denied')).toBeVisible();
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/audit-logs'))).toBe(false);
  });

  it('downloads CSV using the bearer and applied filters', async () => {
    const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test');
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const fetch = mount();
    await screen.findByText('Login succeeded');
    await userEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    await waitFor(() => expect(revoke).toHaveBeenCalledWith('blob:test'));
    const request = fetch.mock.calls.find(([url]) => String(url).includes('format=csv'));
    expect(new Headers(request?.[1]?.headers).get('Authorization')).toBe('Bearer token');
    expect(create).toHaveBeenCalled();
    click.mockRestore();
  });

  it('does not show export when export permission is missing', async () => {
    mount({ ...identity, permissions: ['view'] });
    await screen.findByText('Login succeeded');
    expect(screen.queryByRole('button', { name: 'Export CSV' })).not.toBeInTheDocument();
  });
});
