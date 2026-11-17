/** Exercise dashboard rendering, filter navigation and access at the HTTP boundary. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../../App';
import { TOKEN_KEY } from '../../shared/api';
import type { ExecutiveDashboard, User } from '../../types';
import { landingPath } from './dashboardApi';

const id = '507f1f77bcf86cd799439011';
const identity: User = { id, name: 'Executive', email: 'executive@ketsip.local', role: 'Executive', permissions: ['view'],
  portfolioAccess: [], status: 'Active', lastLogin: null, authSource: 'local', managerName: null,
  vendorIndicator: false, defaultLandingPage: null, mustChangePassword: false,
  createdAt: '2025-01-01T00:00:00Z', updatedAt: '2025-01-01T00:00:00Z' };
const dashboard: ExecutiveDashboard = { enterpriseQualityScore: 41, applicationHealthScore: 61, automationMaturityScore: 21,
  openCriticalDefects: 5, applicationsAtRisk: 1, totalApplications: 2, totalPortfolios: 2,
  portfolios: [{ id, name: 'Payments', applicationCount: 2, qualityScore: 41, highRiskCount: 1 },
    { id: '507f1f77bcf86cd799439012', name: 'Empty', applicationCount: 0, qualityScore: null, highRiskCount: 0 }] };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });

/** Mount the real router with a replaceable HTTP boundary. */
function mount(user = identity, path = '/dashboard') {
  localStorage.setItem(TOKEN_KEY, 'token');
  window.history.replaceState(null, '', path);
  const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async input =>
    String(input).endsWith('/auth/me') ? json(user) : json(dashboard));
  render(<App />);
  return fetch;
}
beforeEach(() => localStorage.clear());

describe('Executive dashboard', () => {
  it('renders real scalar and portfolio values, including null quality', async () => {
    mount();
    const metrics = await screen.findByRole('region', { name: 'Executive metrics' });
    for (const [label, value] of [['Enterprise Quality Score', '41'], ['Application Health Score', '61'],
      ['Automation Maturity Score', '21'], ['Open Critical Defects', '5'], ['Applications at Risk', '1'],
      ['Total Applications', '2'], ['Total Portfolios', '2']]) {
      expect(within(metrics).getByText(label).parentElement).toHaveTextContent(value);
    }
    expect(screen.getByText('Quality score: N/A')).toBeVisible();
    expect(screen.getByText('High-risk applications: 1')).toBeVisible();
  });

  it('applies all filters to the URL and clears them', async () => {
    const fetch = mount();
    const user = userEvent.setup();
    await screen.findByRole('option', { name: 'Payments' });
    await user.selectOptions(screen.getByLabelText('Portfolio filter'), id);
    await user.type(screen.getByLabelText('Product area filter'), 'Finance');
    await user.selectOptions(screen.getByLabelText('Risk level filter'), 'High');
    await user.click(screen.getByRole('button', { name: 'Apply filters' }));
    await waitFor(() => expect(window.location.search).toContain('riskLevel=High'));
    expect(window.location.search).toContain(`portfolioId=${id}`);
    expect(window.location.search).toContain('productArea=Finance');
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).includes('riskLevel=High'))).toBe(true));
    await user.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(window.location.search).toBe('');
  });

  it('shows null averages and an empty message without inventing scores', async () => {
    const fetch = mount();
    fetch.mockImplementation(async input => String(input).endsWith('/auth/me') ? json(identity) : json({
      ...dashboard, enterpriseQualityScore: null, applicationHealthScore: null, automationMaturityScore: null,
      openCriticalDefects: 0, applicationsAtRisk: 0, totalApplications: 0, totalPortfolios: 0, portfolios: [],
    }));
    expect(await screen.findByText('No visible applications.')).toBeVisible();
    expect(screen.getAllByText('N/A')).toHaveLength(3);
    expect(screen.getByText('No visible portfolios match this selection.')).toBeVisible();
  });

  it('shows a recoverable error and denies access without view', async () => {
    const fetch = mount();
    fetch.mockImplementation(async input => String(input).endsWith('/auth/me') ? json(identity) : json({ detail: 'Unavailable' }, 503));
    expect(await screen.findByRole('button', { name: 'Retry dashboard' })).toBeVisible();
    fetch.mockImplementation(async input => String(input).endsWith('/auth/me') ? json(identity) : json(dashboard));
    await userEvent.setup().click(screen.getByRole('button', { name: 'Retry dashboard' }));
    expect(await screen.findByText('High-risk applications: 1')).toBeVisible();
  });

  it('does not fetch dashboard without view permission', async () => {
    const fetch = mount({ ...identity, permissions: [] });
    expect(await screen.findByRole('alert')).toHaveTextContent('Access denied');
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/dashboard/executive'))).toBe(false);
  });

  it('selects role defaults, saved preferences, and forced or denied fallbacks', () => {
    expect(landingPath(identity)).toBe('/dashboard');
    expect(landingPath({ ...identity, role: 'Engineer' })).toBe('/applications');
    expect(landingPath({ ...identity, role: 'Engineer', defaultLandingPage: 'dashboard' })).toBe('/dashboard');
    expect(landingPath({ ...identity, defaultLandingPage: 'applications' })).toBe('/applications');
    expect(landingPath({ ...identity, permissions: [] })).toBe('/account');
    expect(landingPath({ ...identity, mustChangePassword: true })).toBe('/profile');
  });
});
