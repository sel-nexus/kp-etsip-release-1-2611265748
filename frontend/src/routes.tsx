/** Define only available public pages and the live identity/session account view. */
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import EntryPage from './features/auth/EntryPage';
import LoginPage from './features/auth/LoginPage';
import ProfilePage from './features/profile/ProfilePage';
import PortfoliosPage from './features/portfolios/PortfoliosPage';
import PortfolioDetailPage from './features/portfolios/PortfolioDetailPage';
import { useAuth } from './features/auth/AuthProvider';
import { Shell } from './shared/Shell';
import { Button } from './shared/Button';
import { useEffect } from 'react';

/** Reject unauthenticated navigation and offer retry for recoverable identity reads. */
function Protected() {
  const location = useLocation();
  const { user, loading, error, refresh } = useAuth();
  if (loading) return <main className="container" role="status">Verifying session…</main>;
  if (error) return (
    <main className="container">
      <p role="alert" className="error">{error}</p>
      <Button onClick={() => void refresh()}>Retry session</Button>
      <Link to="/login">Sign in</Link>
    </main>
  );
  if (user?.mustChangePassword && location.pathname !== '/profile') return <Navigate to="/profile" replace />;
  return user ? <Shell /> : <Navigate to="/login" replace />;
}
/** Render account fields supplied by the real me endpoint, not a future-feature stub. */
function AccountPage() {
  const { user, refresh, loading } = useAuth();
  if (!user) return null;
  const scope = user.portfolioAccess.length ? user.portfolioAccess.join(', ') :
    ['Administrator', 'Executive', 'Auditor'].includes(user.role) ? 'All portfolios' : 'No assigned portfolios';
  return (
    <>
      <h1>Account &amp; session</h1>
      <p className="muted">Your current local identity and effective access.</p>
      <section className="card" aria-label="Current identity">
        <dl>
          <dt>Name</dt><dd>{user.name}</dd>
          <dt>Email</dt><dd>{user.email}</dd>
          <dt>Role</dt><dd>{user.role}</dd>
          <dt>Portfolio access</dt><dd>{scope}</dd>
          <dt>Permissions</dt><dd>{user.permissions.join(', ') || 'None'}</dd>
          <dt>Account status</dt><dd>{user.status}</dd>
          <dt>Authentication</dt><dd>Local email and password</dd>
          <dt>Last sign-in</dt><dd>{user.lastLogin ? new Date(user.lastLogin).toLocaleString() : 'No previous sign-in'}</dd>
          <dt>Landing preference</dt><dd>{user.defaultLandingPage || 'Role default'}</dd>
        </dl>
      </section>
      <p className="muted">
        Portfolio inventory is available. Application and insight pages are not yet available. Your landing preference is saved for those pages when available.
      </p>
      <p><Link to="/profile">Manage profile and password</Link></p>
      <Button variant="secondary" onClick={() => void refresh()} pending={loading}>Refresh identity</Button>
    </>
  );
}
/** Display session feedback across redirects while retaining native sign-out messages. */
function LoginRoute() {
  const location = useLocation();
  const { sessionMessage } = useAuth();
  const message = sessionMessage || (location.state as { message?: string } | null)?.message;
  return (
    <>
      {message && <p className="container" role="status">{message}</p>}
      <LoginPage />
    </>
  );
}
/** Map a single router's locations to complete existing pages. */
export function AppRoutes() {
  const location = useLocation();
  useEffect(() => {
    const titles: Record<string, string> = { '/': 'Enterprise access', '/login': 'Sign in', '/account': 'Account & session', '/profile': 'My Profile', '/portfolios': 'Portfolios' };
    document.title = `${titles[location.pathname] || (location.pathname.startsWith('/portfolios/') ? 'Portfolio detail' : 'Page not found')} · KP ETSIP`;
  }, [location.pathname]);
  return (
    <Routes>
      <Route path="/" element={<EntryPage />} />
      <Route path="/login" element={<LoginRoute />} />
      <Route element={<Protected />}>
        <Route path="/account" element={<AccountPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/portfolios" element={<PortfoliosPage />} />
        <Route path="/portfolios/:id" element={<PortfolioDetailPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
