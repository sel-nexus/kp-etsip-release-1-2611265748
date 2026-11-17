/** Exercise auth UI through real components and mocked fetch boundaries only. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../../App';
import type { User } from '../../types';
import { TOKEN_KEY } from '../../shared/api';

const identity: User = {
  id: '507f1f77bcf86cd799439011', name: 'Live Executive', email: 'executive@ketsip.local',
  role: 'Executive', permissions: ['view', 'export'], portfolioAccess: [], status: 'Active',
  lastLogin: '2025-05-01T12:00:00Z', authSource: 'local', managerName: null,
  vendorIndicator: false, defaultLandingPage: null, mustChangePassword: false,
  createdAt: '2025-05-01T12:00:00Z', updatedAt: '2025-05-01T12:00:00Z',
};
/** Return a JSON HTTP response from the network test boundary. */
function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
}
/** Enter the app at a chosen initial browser location. */
function mount(path = '/') {
  window.history.replaceState(null, '', path);
  return render(<App />);
}
/** Fill the visible credential fields through normal user interaction. */
async function fillLogin() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Email'), 'executive@ketsip.local');
  await user.type(screen.getByLabelText('Password'), 'ConfiguredPassword123!');
  return user;
}
beforeEach(() => localStorage.clear());

describe('Local identity', () => {
  it('offers native entry navigation and validates both fields without network', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch');
    const user = userEvent.setup();
    mount();
    expect(screen.queryByRole('link', { name: /sign up/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: 'Sign in' }));
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(screen.getByText('Enter a valid email address.')).toBeVisible();
    expect(screen.getByText('Enter your password.')).toBeVisible();
    expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('renders credential rejection without clearing a session through the global handler', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: 'Invalid email or password' }, 401));
    mount('/login');
    const user = await fillLogin();
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password');
    expect(window.location.pathname).toBe('/login');
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it('shows pending submission and routes actual server identity to account', async () => {
    let resolve!: (response: Response) => void;
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(() => new Promise<Response>((done) => { resolve = done; }));
    mount('/login');
    const user = await fillLogin();
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(screen.getByRole('button', { name: 'Signing in…' })).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent('Verifying your credentials');
    resolve(json({ token: 'server-issued-token', user: identity }));
    expect(await screen.findByRole('heading', { name: 'Account & session' })).toBeVisible();
    expect(screen.getByText('Live Executive', { selector: 'dd' })).toBeVisible();
    expect(screen.getByText(identity.email)).toBeVisible();
    expect(localStorage.getItem(TOKEN_KEY)).toBe('server-issued-token');
    expect(window.location.pathname).toBe('/account');
    const init = fetch.mock.calls[0][1];
    expect(JSON.parse(init?.body as string)).toEqual({ email: identity.email, password: 'ConfiguredPassword123!' });
  });

  it.each(['Administrator', 'Engineer', 'Auditor', 'Read Only', 'Portfolio Leader'] as const)(
    'routes %s to the appropriate available landing page', async (role) => {
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
        if (String(url).includes('/auth/login')) return json({ token: 'server-token', user: { ...identity, role, mustChangePassword: role === 'Administrator' } });
        return json({ items: [], total: 0, page: 1, pageSize: 25 });
      });
      mount('/login');
      const user = await fillLogin();
      await user.click(screen.getByRole('button', { name: 'Sign in' }));
      expect(await screen.findByRole('heading', { name: role === 'Administrator' ? 'My Profile' : 'Applications' })).toBeVisible();
      if (role === 'Administrator') {
        expect(screen.getByText(role, { selector: 'dd' })).toBeVisible();
        expect(screen.getByText(/Password change is required/)).toBeVisible();
      } else {
        expect(window.location.pathname).toBe('/applications');
        expect(await screen.findByText('No visible applications.')).toBeVisible();
      }
    },
  );

  it('redirects unauthenticated protected entry to sign-in', async () => {
    mount('/account');
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeVisible();
    expect(window.location.pathname).toBe('/login');
  });

  it('restores identity with bearer and removes it on confirmed logout', async () => {
    localStorage.setItem(TOKEN_KEY, 'persisted-token');
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json(identity)).mockResolvedValueOnce(new Response(null, { status: 204 }));
    mount('/account');
    expect(await screen.findByRole('heading', { name: 'Account & session' })).toBeVisible();
    expect(new Headers(fetch.mock.calls[0][1]?.headers).get('Authorization')).toBe('Bearer persisted-token');
    await userEvent.setup().click(screen.getByRole('button', { name: 'Sign out' }));
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeVisible();
    expect(screen.getByRole('status')).toHaveTextContent('Signed out.');
    expect(fetch.mock.calls[1][0]).toBe('/api/auth/logout');
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it('clears locally on failed logout but discloses unconfirmed server revocation', async () => {
    localStorage.setItem(TOKEN_KEY, 'persisted-token');
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json(identity)).mockRejectedValueOnce(new TypeError('offline'));
    mount('/account');
    await screen.findByRole('heading', { name: 'Account & session' });
    await userEvent.setup().click(screen.getByRole('button', { name: 'Sign out' }));
    expect(await screen.findByText(/Server revocation could not be confirmed/)).toBeVisible();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it('rejects a revoked stored bearer and never flashes protected identity', async () => {
    localStorage.setItem(TOKEN_KEY, 'revoked-token');
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: 'Invalid or expired session' }, 401));
    mount('/account');
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeVisible();
    expect(screen.queryByText('Live Executive')).not.toBeInTheDocument();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it('offers a session retry after transport failure and then renders current identity', async () => {
    localStorage.setItem(TOKEN_KEY, 'persisted-token');
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new TypeError('offline')).mockResolvedValueOnce(json(identity));
    mount('/account');
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to reach the service');
    await userEvent.setup().click(screen.getByRole('button', { name: 'Retry session' }));
    expect(await screen.findByRole('heading', { name: 'Account & session' })).toBeVisible();
  });

  it('supports collapsing native account navigation', async () => {
    localStorage.setItem(TOKEN_KEY, 'persisted-token');
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(identity));
    mount('/account');
    await screen.findByRole('heading', { name: 'Account & session' });
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Hide navigation' }));
    expect(screen.queryByRole('navigation', { name: 'Account' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Show navigation' }));
    expect(screen.getByRole('link', { name: 'Account & session' })).toHaveAttribute('aria-current', 'page');
  });
});
