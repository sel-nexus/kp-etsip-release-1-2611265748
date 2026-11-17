/** Verify self-service behavior through actual components and fetch-only mocks. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../../App';
import type { User } from '../../types';
import { TOKEN_KEY } from '../../shared/api';

const identity: User = {
  id: '507f1f77bcf86cd799439011', name: 'Profile Administrator', email: 'admin@ketsip.local',
  role: 'Administrator', permissions: ['view', 'edit', 'administer'], portfolioAccess: [], status: 'Active',
  lastLogin: null, authSource: 'local', managerName: null, vendorIndicator: false,
  defaultLandingPage: 'dashboard', mustChangePassword: false,
  createdAt: '2025-05-01T12:00:00Z', updatedAt: '2025-05-01T12:00:00Z',
};
/** Build a response at the sole mocked network boundary. */
function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status });
}
/** Mount a real protected app with a stored server token. */
function mount(path = '/profile') {
  localStorage.setItem(TOKEN_KEY, 'real-boundary-token');
  window.history.replaceState(null, '', path);
  return render(<App />);
}
/** Fill all password inputs with normal keyboard interactions. */
async function fillPassword(current = 'CurrentPassword123!', next = 'ReplacementPassword123!', confirm = next) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Current password'), current);
  await user.type(screen.getByLabelText('New password'), next);
  await user.type(screen.getByLabelText('Confirm new password'), confirm);
  return user;
}
beforeEach(() => localStorage.clear());

describe('My Profile', () => {
  it('renders live identity, all-portfolio access and the persisted selection', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(identity));
    mount();
    expect(await screen.findByRole('heading', { name: 'My Profile' })).toBeVisible();
    expect(screen.getByText(identity.name, { selector: 'dd' })).toBeVisible();
    expect(screen.getByText(identity.email)).toBeVisible();
    expect(screen.getByText('Administrator', { selector: 'dd' })).toBeVisible();
    expect(screen.getByText('All portfolios')).toBeVisible();
    expect(screen.getByRole('radio', { name: 'Executive dashboard' })).toBeChecked();
    expect(document.title).toBe('My Profile · KP ETSIP');
  });

  it.each([{ portfolioAccess: [] as string[] }, { portfolioAccess: ['507f1f77bcf86cd799439012'] }])(
    'displays restricted portfolio scope $portfolioAccess', async ({ portfolioAccess }) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ...identity, role: 'Engineer', portfolioAccess }));
    mount();
    expect(await screen.findByText(portfolioAccess.length ? portfolioAccess[0] : 'No assigned portfolios')).toBeVisible();
  });

  it('navigates from account through a real profile link and back', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(identity));
    mount('/account');
    await screen.findByRole('heading', { name: 'Account & session' });
    const user = userEvent.setup();
    await user.click(screen.getByRole('link', { name: 'Manage profile and password' }));
    expect(screen.getByRole('heading', { name: 'My Profile' })).toBeVisible();
    await user.click(screen.getByRole('link', { name: 'Account & session' }));
    expect(screen.getByRole('heading', { name: 'Account & session' })).toBeVisible();
  });

  it('forces a restored admin session from account to profile and hides other navigation', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ...identity, mustChangePassword: true }));
    mount('/account');
    expect(await screen.findByRole('heading', { name: 'My Profile' })).toBeVisible();
    expect(window.location.pathname).toBe('/profile');
    expect(screen.getByText(/Password change is required before business access/)).toBeVisible();
    expect(screen.queryByRole('link', { name: 'Account & session' })).not.toBeInTheDocument();
  });

  it('routes a newly signed-in forced admin to profile', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ token: 'new-token', user: { ...identity, mustChangePassword: true } }));
    window.history.replaceState(null, '', '/login');
    render(<App />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Email'), identity.email);
    await user.type(screen.getByLabelText('Password'), 'CurrentPassword123!');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { name: 'My Profile' })).toBeVisible();
    expect(window.location.pathname).toBe('/profile');
  });

  it('shows loading, saves a preference with bearer, and retains it on revisit', async () => {
    let resolve!: (response: Response) => void;
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json(identity))
      .mockImplementationOnce(() => new Promise<Response>((done) => { resolve = done; }));
    mount();
    await screen.findByRole('heading', { name: 'My Profile' });
    const user = userEvent.setup();
    await user.click(screen.getByRole('radio', { name: 'Applications' }));
    await user.click(screen.getByRole('button', { name: 'Save preference' }));
    expect(screen.getByRole('button', { name: 'Saving preference…' })).toBeDisabled();
    expect(screen.getByText('Saving your landing preference…')).toBeVisible();
    await act(async () => resolve(json({ ...identity, defaultLandingPage: 'applications' })));
    expect(await screen.findByText('Landing preference saved.')).toBeVisible();
    expect(fetch.mock.calls[1][0]).toBe('/api/auth/profile');
    expect(fetch.mock.calls[1][1]?.method).toBe('PUT');
    expect(new Headers(fetch.mock.calls[1][1]?.headers).get('Authorization')).toBe('Bearer real-boundary-token');
    expect(JSON.parse(fetch.mock.calls[1][1]?.body as string)).toEqual({ defaultLandingPage: 'applications' });
    await user.click(screen.getByRole('link', { name: 'Account & session' }));
    await user.click(screen.getByRole('link', { name: 'My Profile' }));
    expect(screen.getByRole('radio', { name: 'Applications' })).toBeChecked();
  });

  it('requires a selection for an unset role default', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ...identity, defaultLandingPage: null }));
    mount();
    await screen.findByRole('heading', { name: 'My Profile' });
    await userEvent.setup().click(screen.getByRole('button', { name: 'Save preference' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a landing page.');
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.each([503, 422, 0])('shows preference failure %s and offers resubmission', async (status) => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json(identity));
    if (status) fetch.mockResolvedValueOnce(json({ detail: [] }, status));
    else fetch.mockRejectedValueOnce(new TypeError('offline'));
    fetch.mockResolvedValueOnce(json(identity));
    mount();
    await screen.findByRole('heading', { name: 'My Profile' });
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Save preference' }));
    expect(await screen.findByRole('alert')).toBeVisible();
    expect(screen.queryByText('Landing preference saved.')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Save preference' }));
    expect(await screen.findByText('Landing preference saved.')).toBeVisible();
  });

  it('associates missing password errors and does not submit', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(identity));
    mount();
    await screen.findByRole('heading', { name: 'My Profile' });
    await userEvent.setup().click(screen.getByRole('button', { name: 'Change password' }));
    expect(screen.getByLabelText('Current password')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('New password')).toHaveAttribute('aria-describedby', 'new-password-error');
    expect(screen.getByText('Passwords must match.')).toBeVisible();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.each(['short', 'é'.repeat(37), 'x'.repeat(73)])('rejects invalid new-password byte length %s', async (next) => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(identity));
    mount();
    await screen.findByRole('heading', { name: 'My Profile' });
    const user = await fillPassword('CurrentPassword123!', next);
    await user.click(screen.getByRole('button', { name: 'Change password' }));
    expect(screen.getByText('New password must contain 12–72 UTF-8 bytes.')).toBeVisible();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('rejects reuse and mismatched confirmation locally', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(identity));
    mount();
    await screen.findByRole('heading', { name: 'My Profile' });
    const user = await fillPassword('CurrentPassword123!', 'CurrentPassword123!', 'DifferentPassword123!');
    await user.click(screen.getByRole('button', { name: 'Change password' }));
    expect(screen.getByText('New password must differ from current password.')).toBeVisible();
    expect(screen.getByText('Passwords must match.')).toBeVisible();
  });

  it('shows incorrect-current field error while preserving the live session', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json(identity)).mockResolvedValueOnce(json({ detail: 'Current password is incorrect' }, 400));
    mount();
    await screen.findByRole('heading', { name: 'My Profile' });
    const user = await fillPassword();
    await user.click(screen.getByRole('button', { name: 'Change password' }));
    expect(await screen.findByText('Current password is incorrect')).toBeVisible();
    expect(screen.getByLabelText('Current password')).toHaveAttribute('aria-invalid', 'true');
    expect(localStorage.getItem(TOKEN_KEY)).toBe('real-boundary-token');
  });

  it.each([422, 503, 0])('shows password failure %s without success navigation', async (status) => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json(identity));
    if (status) fetch.mockResolvedValueOnce(json({ detail: [] }, status));
    else fetch.mockRejectedValueOnce(new TypeError('offline'));
    mount();
    await screen.findByRole('heading', { name: 'My Profile' });
    const user = await fillPassword();
    await user.click(screen.getByRole('button', { name: 'Change password' }));
    expect(await screen.findByRole('alert')).toBeVisible();
    expect(window.location.pathname).toBe('/profile');
    expect(screen.getByRole('button', { name: 'Change password' })).toBeEnabled();
  });

  it('shows password pending then clears token and requires sign-in after 204', async () => {
    let resolve!: (response: Response) => void;
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json(identity))
      .mockImplementationOnce(() => new Promise<Response>((done) => { resolve = done; }));
    mount();
    await screen.findByRole('heading', { name: 'My Profile' });
    const user = await fillPassword();
    await user.click(screen.getByRole('button', { name: 'Change password' }));
    expect(screen.getByRole('button', { name: 'Changing password…' })).toBeDisabled();
    expect(screen.getByText('Updating password and revoking prior sessions…')).toBeVisible();
    await act(async () => resolve(new Response(null, { status: 204 })));
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeVisible();
    expect(screen.getByText('Password changed. Sign in again with your new password.')).toBeVisible();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(fetch.mock.calls[1][0]).toBe('/api/auth/change-password');
    expect(JSON.parse(fetch.mock.calls[1][1]?.body as string)).toEqual({ currentPassword: 'CurrentPassword123!', newPassword: 'ReplacementPassword123!' });
    expect(fetch.mock.calls.some(([path]) => path === '/api/auth/logout')).toBe(false);
  });

  it('clears a revoked bearer when a mutation returns 401', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json(identity)).mockResolvedValueOnce(json({ detail: 'Invalid or expired session' }, 401));
    mount();
    await screen.findByRole('heading', { name: 'My Profile' });
    await userEvent.setup().click(screen.getByRole('button', { name: 'Save preference' }));
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeVisible();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it('shows identity loading and retry rather than rendering a partial profile', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new TypeError('offline')).mockResolvedValueOnce(json(identity));
    mount();
    expect(screen.getByRole('status')).toHaveTextContent('Verifying session');
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to reach the service');
    await userEvent.setup().click(screen.getByRole('button', { name: 'Retry session' }));
    expect(await screen.findByRole('heading', { name: 'My Profile' })).toBeVisible();
  });
});
