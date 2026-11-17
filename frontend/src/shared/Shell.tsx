/** Render native account navigation and revoking sign-out with visible feedback. */
import { useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { Button } from './Button';
import { useAuth } from '../features/auth/AuthProvider';
/** Provide only currently implemented navigation; no future-feature links. */
export function Shell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [pending, setPending] = useState(false);
  const [expanded, setExpanded] = useState(true);
  /** Revoke server tokens and communicate incomplete network revocation after clearing locally. */
  const signOut = async () => {
    setPending(true);
    try {
      await logout();
      navigate('/login', { replace: true, state: { message: 'Signed out.' } });
    } catch {
      navigate('/login', { replace: true, state: { message: 'Signed out locally. Server revocation could not be confirmed; previous tokens may remain valid until expiry.' } });
    } finally { setPending(false); }
  };
  return (
    <>
      <a href="#main" className="skip-link">Skip to content</a>
      <header className="header">
        <Link className="brand" to="/">KP ETSIP</Link>
        <span className="muted">{user?.name}</span>
        <Button variant="secondary" onClick={signOut} pending={pending}>
          {pending ? 'Signing out…' : 'Sign out'}
        </Button>
      </header>
      <div className="container shell-grid">
        <aside>
          <Button variant="secondary" aria-expanded={expanded} aria-controls="account-nav" onClick={() => setExpanded(!expanded)}>
            {expanded ? 'Hide navigation' : 'Show navigation'}
          </Button>
          <nav id="account-nav" className="shell-nav" aria-label="Account" hidden={!expanded}>
            {!user?.mustChangePassword && <NavLink to="/account">Account &amp; session</NavLink>}
            {!user?.mustChangePassword && user?.permissions.includes('view') && <NavLink to="/dashboard">Executive dashboard</NavLink>}
            {!user?.mustChangePassword && user?.permissions.includes('view') && <NavLink to="/portfolios">Portfolios</NavLink>}
            {!user?.mustChangePassword && user?.permissions.includes('view') && <NavLink to="/applications">Applications</NavLink>}
            {!user?.mustChangePassword && user?.permissions.includes('view') && <NavLink to="/reports">Reports</NavLink>}
            {!user?.mustChangePassword && user?.role === 'Administrator' && user.permissions.includes('administer') && <NavLink to="/administration">Administration</NavLink>}
            {!user?.mustChangePassword && user && ['Administrator', 'Auditor'].includes(user.role) && user.permissions.includes('view') && <NavLink to="/audit">Audit</NavLink>}
            <NavLink to="/profile">My Profile</NavLink>
          </nav>
        </aside>
        <main id="main"><Outlet /></main>
      </div>
    </>
  );
}
