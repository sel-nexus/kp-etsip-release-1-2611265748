/** Provide the concise product entry without signup or marketing expansion. */
import { Link } from 'react-router-dom';
import { useAuth } from './AuthProvider';
/** Offer native navigation to sign-in or the current session. */
export default function EntryPage() {
  const { user } = useAuth();
  return (
    <main id="main" className="container public-page">
      <p className="muted">KP ETSIP · Release 1</p>
      <h1>Enterprise quality inventory &amp; insight</h1>
      <p>Internal account access for your enterprise inventory and quality information.</p>
      <Link className="button button-primary" to={user ? '/account' : '/login'}>
        {user ? 'View account' : 'Sign in'}
      </Link>
    </main>
  );
}
