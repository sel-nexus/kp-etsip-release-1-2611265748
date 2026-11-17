/** Exercise inventory UI through the real API client and mocked fetch boundary. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../../App';
import { TOKEN_KEY } from '../../shared/api';
import type { Portfolio, User } from '../../types';

const id = '507f1f77bcf86cd799439011';
const identity: User = {
  id, name: 'Admin', email: 'admin@ketsip.local', role: 'Administrator',
  permissions: ['view', 'create', 'edit', 'delete'], portfolioAccess: [], status: 'Active',
  lastLogin: null, authSource: 'local', managerName: null, vendorIndicator: false,
  defaultLandingPage: null, mustChangePassword: false, createdAt: '2025-01-01T00:00:00Z', updatedAt: '2025-01-01T00:00:00Z',
};
const item: Portfolio = { id, name: 'Payments', owner: 'Owner', description: 'Description', productArea: 'Finance', status: 'Active', applicationCount: 0, qualityScore: null, createdAt: '2025-01-01T00:00:00Z', updatedAt: '2025-01-01T00:00:00Z' };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const page = (items: unknown[]) => ({ items, total: items.length, page: 1, pageSize: 25 });
function mount(path: string, user = identity) {
  localStorage.setItem(TOKEN_KEY, 'test-token');
  window.history.replaceState(null, '', path);
  const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith('/auth/me')) return json(user);
    if (url.includes('/applications')) return json(page([]));
    if (url.includes(`/portfolios/${id}`)) {
      if (init?.method === 'PUT') return json({ ...item, ...JSON.parse(String(init.body)) });
      return json(item);
    }
    if (url.includes('/portfolios')) return json(page([item]));
    return json({ detail: 'Unexpected request' }, 500);
  });
  render(<App />);
  return fetch;
}
beforeEach(() => localStorage.clear());

describe('Portfolio inventory', () => {
  it('renders data and applies URL-based filters to the fetch boundary', async () => {
    const fetch = mount('/portfolios');
    const user = userEvent.setup();
    expect(await screen.findByRole('link', { name: 'Payments' })).toBeVisible();
    expect(screen.getByText('N/A')).toBeVisible();
    await user.type(screen.getByLabelText('Search portfolios'), 'Pay');
    await user.type(screen.getByLabelText('Product area filter'), 'Finance');
    await user.selectOptions(screen.getByLabelText('Status filter'), 'Active');
    await user.click(screen.getByRole('button', { name: 'Apply filters' }));
    await waitFor(() => expect(window.location.search).toContain('search=Pay'));
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).includes('productArea=Finance'))).toBe(true));
  });

  it('validates required name and displays server conflict without losing input', async () => {
    const fetch = mount('/portfolios');
    await screen.findByRole('link', { name: 'Payments' });
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Create portfolio' }));
    await user.click(screen.getByRole('button', { name: 'Save portfolio' }));
    expect(screen.getByText('Name is required.')).toBeVisible();
    fetch.mockImplementation(async (input, init) => {
      if (init?.method === 'POST') return json({ detail: 'Portfolio name already exists' }, 409);
      if (String(input).endsWith('/auth/me')) return json(identity);
      return json(page([item]));
    });
    await user.type(screen.getByLabelText('Name'), 'Payments');
    await user.click(screen.getByRole('button', { name: 'Save portfolio' }));
    expect(await screen.findByText('Portfolio name already exists')).toBeVisible();
    expect(screen.getByLabelText('Name')).toHaveValue('Payments');
  });

  it('sends only writable fields on edit and reloads the persisted detail', async () => {
    const fetch = mount(`/portfolios/${id}`);
    await screen.findByRole('heading', { name: 'Payments' });
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Edit portfolio' }));
    await user.clear(screen.getByLabelText('Owner'));
    await user.type(screen.getByLabelText('Owner'), 'New owner');
    await user.click(screen.getByRole('button', { name: 'Save portfolio' }));
    await waitFor(() => expect(fetch.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(true));
    const call = fetch.mock.calls.find(([, init]) => init?.method === 'PUT');
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ name: 'Payments', owner: 'New owner', description: 'Description', productArea: 'Finance', status: 'Active' });
    expect(await screen.findByText('Portfolio saved.')).toBeVisible();
  });

  it('hides mutation controls from read-only identity and shows linked empty state', async () => {
    mount(`/portfolios/${id}`, { ...identity, role: 'Read Only', permissions: ['view'], portfolioAccess: [id] });
    await screen.findByRole('heading', { name: 'Payments' });
    expect(await screen.findByText('No linked applications.')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Edit portfolio' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete portfolio' })).not.toBeInTheDocument();
  });

  it('offers retry when list loading fails', async () => {
    const fetch = mount('/portfolios');
    fetch.mockImplementation(async (input) => String(input).endsWith('/auth/me') ? json(identity) : json({ detail: 'Unavailable' }, 503));
    expect(await screen.findByRole('alert')).toHaveTextContent('Unavailable');
    fetch.mockImplementation(async (input) => String(input).endsWith('/auth/me') ? json(identity) : json(page([item])));
    await userEvent.setup().click(screen.getByRole('button', { name: 'Retry portfolios' }));
    expect(await screen.findByRole('link', { name: 'Payments' })).toBeVisible();
  });
});
