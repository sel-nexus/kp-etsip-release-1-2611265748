/** Verify report navigation, filtering, downloads, errors, and access. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../../App';
import { TOKEN_KEY } from '../../shared/api';
import type { User } from '../../types';

const identity: User = { id: '507f1f77bcf86cd799439011', name: 'Executive', email: 'executive@ketsip.local', role: 'Executive', permissions: ['view', 'export'], portfolioAccess: [], status: 'Active', lastLogin: null, authSource: 'local', managerName: null, vendorIndicator: false, defaultLandingPage: null, mustChangePassword: false, createdAt: '2025-01-01T00:00:00Z', updatedAt: '2025-01-01T00:00:00Z' };
const application = { id: '507f1f77bcf86cd799439012', name: 'Gateway', portfolioId: '507f1f77bcf86cd799439013', portfolioName: 'Payments', criticality: 'High', tier: 1, lifecycleStatus: 'Active', applicationHealthScore: 90, automationCoverage: 80, openCriticalDefects: 1, riskLevel: 'High' };
const portfolio = { id: application.portfolioId, name: 'Payments', owner: 'Owner', productArea: 'Finance', applicationCount: 4, qualityScore: 85, status: 'Active' };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
/** Replace only the HTTP boundary while exercising the actual routes. */
function mount(user = identity, fail = false, path = '/reports?report=applications') {
  localStorage.setItem(TOKEN_KEY, 'token');
  window.history.replaceState(null, '', path);
  const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const url = String(input);
    if (url.endsWith('/auth/me')) return json(user);
    if (url.includes('format=csv')) return fail ? json({ detail: 'Export unavailable' }, 503) : new Response('name\nGateway\n');
    if (fail) return json({ detail: 'Report unavailable' }, 503);
    const item = url.includes('portfolios') ? portfolio : application;
    return json({ items: [item], total: 1, page: 1, pageSize: 25 });
  });
  render(<App />);
  return fetch;
}
beforeEach(() => localStorage.clear());

describe('Reports', () => {
  it('renders both report tables and keeps filters in the URL', async () => {
    const fetch = mount();
    expect(await screen.findByRole('link', { name: 'Gateway' })).toBeVisible();
    await userEvent.type(screen.getByLabelText('Search'), 'Gateway');
    await userEvent.click(screen.getByRole('button', { name: 'Apply filters' }));
    await waitFor(() => expect(window.location.search).toContain('search=Gateway'));
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/reports/applications?') && String(url).includes('search=Gateway'))).toBe(true);
    await userEvent.click(screen.getByRole('link', { name: 'Portfolio Report' }));
    expect(await screen.findByRole('link', { name: 'Payments' })).toBeVisible();
    expect(screen.getByText('Finance')).toBeVisible();
  });
  it('shows report and export failures', async () => {
    mount(identity, true);
    expect(await screen.findByText('Report unavailable')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    expect(await screen.findByText('Export unavailable')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Retry report' })).toBeVisible();
  });
  it('downloads current applied filters with a bearer', async () => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test');
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const fetch = mount(identity, false, '/reports?report=applications&search=Gateway&page=2');
    await screen.findByRole('link', { name: 'Gateway' });
    await userEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    await waitFor(() => expect(revoke).toHaveBeenCalledWith('blob:test'));
    const call = fetch.mock.calls.find(([url]) => String(url).includes('format=csv'));
    expect(String(call?.[0])).toContain('search=Gateway');
    expect(new Headers(call?.[1]?.headers).get('Authorization')).toBe('Bearer token');
  });
  it('exports the application repository current URL filters instead of only its page', async () => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test');
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const fetch = mount(identity, false, '/applications?search=Gateway&riskLevel=High&page=2&pageSize=1');
    await screen.findByRole('link', { name: 'Gateway' });
    await userEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    await waitFor(() => expect(revoke).toHaveBeenCalledWith('blob:test'));
    const call = fetch.mock.calls.find(([url]) => String(url).includes('/reports/applications?') && String(url).includes('format=csv'));
    expect(String(call?.[0])).toContain('search=Gateway');
    expect(String(call?.[0])).toContain('riskLevel=High');
    expect(String(call?.[0])).toContain('page=2');
  });
  it('forbids read-only exports even with generic export granted', async () => {
    mount({ ...identity, role: 'Read Only' });
    await screen.findByRole('link', { name: 'Gateway' });
    expect(screen.queryByRole('button', { name: 'Export CSV' })).not.toBeInTheDocument();
  });
  it('denies view without permission and avoids report calls', async () => {
    const fetch = mount({ ...identity, permissions: ['export'] });
    expect(await screen.findByText('Access denied')).toBeVisible();
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/reports/'))).toBe(false);
  });
});
