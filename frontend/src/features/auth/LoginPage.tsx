/** Render a semantic local credential form with clear pending/error states. */
import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { Button } from '../../shared/Button';
import { FormField } from '../../shared/FormField';
import { useAuth } from './AuthProvider';
import { landingPath } from '../dashboard/dashboardApi';
/** Establish a real local session and route to its currently available account view. */
export default function LoginPage() {
  const auth = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  if (auth.user) return <Navigate to={landingPath(auth.user)} replace />;
  /** Validate local fields, avoid duplicate submission, and disclose server failure. */
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending) return;
    const invalid = {
      email: /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()) ? undefined : 'Enter a valid email address.',
      password: password ? undefined : 'Enter your password.',
    };
    setErrors(invalid);
    setError(null);
    if (invalid.email || invalid.password) return;
    setPending(true);
    try {
      await auth.login({ email: email.trim(), password });
      setPassword('');
      // The identity redirect chooses the authorized landing page.
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Unable to sign in.');
    } finally { setPending(false); }
  };
  return (
    <main id="main" className="container public-page">
      <Link to="/">KP ETSIP</Link>
      <section className="card" aria-labelledby="login-heading">
        <h1 id="login-heading">Sign in</h1>
        <p className="muted">Use your local enterprise account.</p>
        <form onSubmit={submit} noValidate aria-busy={pending}>
          <FormField
            id="email" name="email" label="Email" type="email" autoComplete="username"
            value={email} onChange={(event) => setEmail(event.target.value)} required error={errors.email}
          />
          <FormField
            id="password" name="password" label="Password" type="password" autoComplete="current-password"
            value={password} onChange={(event) => setPassword(event.target.value)} required error={errors.password}
          />
          {error && <p role="alert" className="error">{error}</p>}
          <Button type="submit" pending={pending}>{pending ? 'Signing in…' : 'Sign in'}</Button>
          <p role={pending ? 'status' : undefined} aria-live="polite">{pending ? 'Verifying your credentials…' : ''}</p>
        </form>
        <p className="muted">Local demo: executive@ketsip.local. Use the configured demo password from your setup.</p>
      </section>
    </main>
  );
}
