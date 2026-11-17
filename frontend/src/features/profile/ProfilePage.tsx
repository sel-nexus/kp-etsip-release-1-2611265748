/** Render account access, persisted landing preferences and password lifecycle. */
import { useState } from 'react';
import type { FormEvent } from 'react';
import { Button } from '../../shared/Button';
import { FormField } from '../../shared/FormField';
import { ApiError } from '../../shared/api';
import type { LandingPage } from '../../types';
import { useAuth } from '../auth/AuthProvider';
import { changePassword, saveProfile } from './profileApi';

/** Manage the signed-in account without exposing editable identity or role fields. */
export default function ProfilePage() {
  const { user, updateIdentity, clearSession } = useAuth();
  const [landing, setLanding] = useState<LandingPage | ''>(user?.defaultLandingPage || '');
  const [saving, setSaving] = useState(false);
  const [preferenceError, setPreferenceError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [current, setCurrent] = useState('');
  const [replacement, setReplacement] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [changing, setChanging] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [errors, setErrors] = useState<{ current?: string; replacement?: string; confirmation?: string }>({});
  if (!user) return null;
  const scope = user.portfolioAccess.length ? user.portfolioAccess.join(', ') :
    ['Administrator', 'Executive', 'Auditor'].includes(user.role) ? 'All portfolios' : 'No assigned portfolios';

  /** Save only a supported preference and reflect the returned persisted identity. */
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (saving || changing) return;
    setSaved(false);
    setPreferenceError(null);
    if (!landing) { setPreferenceError('Choose a landing page.'); return; }
    setSaving(true);
    try {
      updateIdentity(await saveProfile({ defaultLandingPage: landing }));
      setSaved(true);
    } catch (failure) {
      setPreferenceError(failure instanceof Error ? failure.message : 'Unable to save preference.');
    } finally { setSaving(false); }
  };

  /** Validate byte bounds and confirmation, then clear the revoked session on success. */
  const change = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (changing || saving) return;
    const bytes = new TextEncoder().encode(replacement).length;
    const currentBytes = new TextEncoder().encode(current).length;
    const invalid = {
      current: currentBytes < 1 || currentBytes > 72 ? 'Enter your current password (1–72 UTF-8 bytes).' : undefined,
      replacement: bytes < 12 || bytes > 72 ? 'New password must contain 12–72 UTF-8 bytes.' :
        replacement === current ? 'New password must differ from current password.' : undefined,
      confirmation: confirmation !== replacement || !confirmation ? 'Passwords must match.' : undefined,
    };
    setErrors(invalid);
    setPasswordError(null);
    if (invalid.current || invalid.replacement || invalid.confirmation) return;
    setChanging(true);
    try {
      await changePassword({ currentPassword: current, newPassword: replacement });
      setCurrent('');
      setReplacement('');
      setConfirmation('');
      clearSession('Password changed. Sign in again with your new password.');
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 400) {
        setErrors({ current: failure.message });
      } else {
        setPasswordError(failure instanceof Error ? failure.message : 'Unable to change password.');
      }
    } finally { setChanging(false); }
  };

  return (
    <>
      <h1>My Profile</h1>
      <p className="muted">Your enterprise identity, portfolio access and sign-in preferences.</p>
      {user.mustChangePassword && (
        <p className="notice" role="status">
          Password change is required before business access. Set a new password below, then sign in again.
        </p>
      )}
      <section className="card" aria-label="Profile identity">
        <h2>Account &amp; access</h2>
        <dl>
          <dt>Name</dt>
          <dd>{user.name}</dd>
          <dt>Email</dt>
          <dd>{user.email}</dd>
          <dt>Role</dt>
          <dd>{user.role}</dd>
          <dt>Portfolio access</dt>
          <dd>{scope}</dd>
        </dl>
      </section>
      <section className="mt-8" aria-labelledby="preference-heading">
        <h2 id="preference-heading">Landing preference</h2>
        <p className="muted">Choose where to start after sign-in. Your selection requires view access.</p>
        <form onSubmit={save} noValidate aria-busy={saving}>
          <fieldset className="card" disabled={saving || changing}>
            <legend>Default landing page</legend>
            <div className="field">
              <label className="flex items-center gap-3">
                <input className="w-auto" type="radio" name="landing" value="dashboard"
                  checked={landing === 'dashboard'} onChange={() => { setLanding('dashboard'); setSaved(false); }} />
                Executive dashboard
              </label>
              <label className="flex items-center gap-3">
                <input className="w-auto" type="radio" name="landing" value="applications"
                  checked={landing === 'applications'} onChange={() => { setLanding('applications'); setSaved(false); }} />
                Applications
              </label>
            </div>
            {preferenceError && <p className="error" role="alert">{preferenceError}</p>}
            <Button variant="secondary" type="submit" pending={saving}>
              {saving ? 'Saving preference…' : 'Save preference'}
            </Button>
          </fieldset>
          <p className="mt-4" role="status" aria-live="polite">
            {saving ? 'Saving your landing preference…' : saved ? 'Landing preference saved.' : ''}
          </p>
        </form>
      </section>
      <section className="mt-8" aria-labelledby="password-heading">
        <h2 id="password-heading">Change password</h2>
        <p className="muted">Use 12–72 UTF-8 bytes. Changing your password signs out all existing sessions.</p>
        <form className="card" onSubmit={change} noValidate aria-busy={changing}>
          <FormField id="current-password" name="currentPassword" label="Current password" type="password" autoComplete="current-password"
            required value={current} disabled={changing || saving} error={errors.current}
            onChange={(event) => setCurrent(event.target.value)} />
          <FormField id="new-password" name="newPassword" label="New password" type="password" autoComplete="new-password"
            required value={replacement} disabled={changing || saving} error={errors.replacement}
            onChange={(event) => setReplacement(event.target.value)} />
          <FormField id="confirm-password" name="confirmPassword" label="Confirm new password" type="password" autoComplete="new-password"
            required value={confirmation} disabled={changing || saving} error={errors.confirmation}
            onChange={(event) => setConfirmation(event.target.value)} />
          {passwordError && <p role="alert" className="error">{passwordError}</p>}
          <Button type="submit" pending={changing} disabled={saving}>
            {changing ? 'Changing password…' : 'Change password'}
          </Button>
          <p className="mt-4" role="status" aria-live="polite">{changing ? 'Updating password and revoking prior sessions…' : ''}</p>
        </form>
      </section>
    </>
  );
}
