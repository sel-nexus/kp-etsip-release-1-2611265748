/** Exercise application screens at the HTTP boundary. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../../App';
import { TOKEN_KEY } from '../../shared/api';
import type { Application, User } from '../../types';

const id = '507f1f77bcf86cd799439011';
const pid = '507f1f77bcf86cd799439012';
const identity: User = { id, name: 'Reader', email: 'reader@ketsip.local', role: 'Read Only', permissions: ['view'],
  portfolioAccess: [pid], status: 'Active', lastLogin: null, authSource: 'local', managerName: null,
  vendorIndicator: false, defaultLandingPage: null, mustChangePassword: false,
  createdAt: '2025-01-01T00:00:00Z', updatedAt: '2025-01-01T00:00:00Z' };
const item: Application = { id, name: 'Gateway', portfolioId: pid, portfolioName: 'Payments', productArea: 'Finance',
  description: 'Payment service', businessOwner: 'Business', technologyOwner: 'Technology', etsOwner: 'Testing',
  criticality: 'Critical', tier: 1, lifecycleStatus: 'Active', technologyStack: 'Python',
  repositoryLink: 'https://example.com/repo', pipelineLink: 'javascript:alert(1)', applicationHealthScore: 80,
  qualityScore: 75, automationCoverage: 60, unitTestCoverage: 65, openDefects: 5, openCriticalDefects: 1,
  riskLevel: 'High', createdAt: '2025-01-01T00:00:00Z', updatedAt: '2025-01-01T00:00:00Z' };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const page = (items: unknown[]) => ({ items, total: items.length, page: 1, pageSize: 25 });

/** Render the real router with a replaceable network boundary. */
function mount(path: string, user = identity) {
  localStorage.setItem(TOKEN_KEY, 'test-token');
  window.history.replaceState(null, '', path);
  const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const url = String(input);
    if (url.endsWith('/auth/me')) return json(user);
    if (url.includes(`/applications/${id}`)) return json(item);
    if (url.includes('/applications')) return json(page([item]));
    if (url.includes('/portfolios')) return json(page([{ id: pid, name: 'Payments' }]));
    return json({ detail: 'Unexpected request' }, 500);
  });
  render(<App />);
  return fetch;
}
beforeEach(() => localStorage.clear());

describe('Application discovery', () => {
  it('applies all filters in the URL and offers real detail navigation', async () => {
    const fetch = mount('/applications');
    const user = userEvent.setup();
    expect(await screen.findByRole('link', { name: 'Gateway' })).toBeVisible();
    await screen.findByRole('option', { name: 'Payments' });
    await user.type(screen.getByLabelText('Search applications'), 'Gate');
    await user.selectOptions(screen.getByLabelText('Portfolio filter'), pid);
    await user.selectOptions(screen.getByLabelText('Criticality filter'), 'Critical');
    await user.selectOptions(screen.getByLabelText('Risk level filter'), 'High');
    await user.selectOptions(screen.getByLabelText('Lifecycle status filter'), 'Active');
    await user.click(screen.getByRole('button', { name: 'Apply filters' }));
    await waitFor(() => expect(window.location.search).toContain('portfolioId=' + pid));
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).includes('riskLevel=High'))).toBe(true));
    await user.click(await screen.findByRole('link', { name: 'Gateway' }));
    expect(await screen.findByRole('heading', { name: 'Gateway' })).toBeVisible();
    expect(screen.getByText('Payment service')).toBeVisible();
    expect(screen.getByText('Business')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Open repository' })).toHaveAttribute('href', 'https://example.com/repo');
    expect(screen.queryByRole('link', { name: 'Open pipeline' })).not.toBeInTheDocument();
  });

  it('shows an empty result and recovers from list errors', async () => {
    const fetch = mount('/applications');
    fetch.mockImplementation(async input => String(input).endsWith('/auth/me') ? json(identity) :
      String(input).includes('/portfolios') ? json(page([])) : json({ detail: 'Unavailable' }, 503));
    expect(await screen.findByText('Unavailable')).toBeVisible();
    fetch.mockImplementation(async input => String(input).endsWith('/auth/me') ? json(identity) : json(page([])));
    await userEvent.setup().click(screen.getByRole('button', { name: 'Retry applications' }));
    expect(await screen.findByText('No visible applications.')).toBeVisible();
  });

  it('shows a detail failure and does not expose inventory without view permission', async () => {
    const fetch = mount(`/applications/${id}`);
    fetch.mockImplementation(async input => String(input).endsWith('/auth/me') ? json(identity) : json({ detail: 'Application not found' }, 404));
    expect(await screen.findByRole('alert')).toHaveTextContent('Application not found');
    expect(screen.getByRole('button', { name: 'Retry application' })).toBeVisible();
  });

  it('denies users without the effective view permission', async () => {
    const fetch = mount('/applications', { ...identity, permissions: [] });
    expect(await screen.findByRole('alert')).toHaveTextContent('Access denied');
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/applications'))).toBe(false);
  });
});
