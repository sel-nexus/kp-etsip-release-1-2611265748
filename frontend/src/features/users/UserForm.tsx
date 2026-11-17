/** Provide labeled account fields and scoped portfolio selection. */
import { useState } from 'react';
import type { FormEvent } from 'react';
import type { Portfolio, RoleName, User, UserWrite } from '../../types';
import { Button } from '../../shared/Button';
import { FormField } from '../../shared/FormField';

interface Props { initial?: User; portfolios: Portfolio[]; manualScope?: boolean; onSave: (value: UserWrite) => Promise<void>; onCancel: () => void }
const roles: RoleName[] = ['Administrator', 'Executive', 'Portfolio Leader', 'Engineer', 'Auditor', 'Read Only'];

/** Retain form input when validation or persistence fails. */
export default function UserForm({ initial, portfolios, manualScope = false, onSave, onCancel }: Props) {
  const [value, setValue] = useState<UserWrite>(initial ? {
    name: initial.name, email: initial.email, role: initial.role, portfolioAccess: initial.portfolioAccess,
    status: initial.status, managerName: initial.managerName, vendorIndicator: initial.vendorIndicator,
  } : { name: '', email: '', role: 'Read Only', portfolioAccess: [], status: 'Active', managerName: null, vendorIndicator: false });
  const [password, setPassword] = useState('');
  const [scopeText, setScopeText] = useState(initial?.portfolioAccess.join(', ') || '');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  /** Check required values and UTF-8 byte limits before submitting. */
  async function submit(event: FormEvent) {
    event.preventDefault();
    const next: Record<string, string> = {};
    if (!value.name.trim() || value.name.trim().length > 200) next.name = 'Enter a name of at most 200 characters.';
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.email.trim()) || value.email.trim().length > 254) next.email = 'Enter a valid email address.';
    const bytes = new TextEncoder().encode(password).length;
    if ((!initial || password) && (bytes < 12 || bytes > 72)) next.password = 'Password must contain 12–72 UTF-8 bytes.';
    const ids = manualScope ? scopeText.split(',').map(id => id.trim()).filter(Boolean) : value.portfolioAccess;
    if (ids.some(id => !/^[0-9a-f]{24}$/i.test(id)) || new Set(ids.map(id => id.toLowerCase())).size !== ids.length) next.scope = 'Enter distinct portfolio IDs separated by commas.';
    setErrors(next);
    if (Object.keys(next).length) return;
    if (initial?.status === 'Active' && value.status === 'Inactive' && !window.confirm(`Deactivate ${initial.name}? Existing sessions will be revoked.`)) return;
    setPending(true);
    setError('');
    try { await onSave({ ...value, portfolioAccess: ids, name: value.name.trim(), email: value.email.trim(), ...(password ? { password } : {}) }); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to save user.'); }
    finally { setPending(false); }
  }
  return (
    <form className="card" aria-label="User form" onSubmit={submit} noValidate>
      <fieldset disabled={pending}>
        <legend>{initial ? 'Edit user' : 'New user'}</legend>
        <FormField id="user-name" label="Name" required value={value.name} error={errors.name}
          onChange={event => setValue({ ...value, name: event.target.value })} />
        <FormField id="user-email" label="Email" type="email" required value={value.email} error={errors.email}
          onChange={event => setValue({ ...value, email: event.target.value })} />
        <FormField id="user-password" label={initial ? 'New password (optional)' : 'Password'} type="password" required={!initial}
          autoComplete="new-password" value={password} error={errors.password} onChange={event => setPassword(event.target.value)} />
        <div className="field">
          <label htmlFor="user-role">Role</label>
          <select id="user-role" value={value.role} onChange={event => setValue({ ...value, role: event.target.value as RoleName })}>
            {roles.map(role => <option key={role}>{role}</option>)}
          </select>
        </div>
        <fieldset>
          <legend>Portfolio access</legend>
          <p className="muted">No selection means all portfolios for Administrator, Executive and Auditor; other roles see none.</p>
          {manualScope && <FormField id="user-scope" label="Portfolio IDs (comma separated)" value={scopeText} error={errors.scope}
            onChange={event => setScopeText(event.target.value)} />}
          {portfolios.map(portfolio => (
            <label key={portfolio.id}>
              <input type="checkbox" checked={value.portfolioAccess.includes(portfolio.id)}
                onChange={event => setValue({ ...value, portfolioAccess: event.target.checked
                  ? [...value.portfolioAccess, portfolio.id] : value.portfolioAccess.filter(id => id !== portfolio.id) })} />
              {' '}{portfolio.name}
            </label>
          ))}
        </fieldset>
        <div className="field">
          <label htmlFor="user-status">Status</label>
          <select id="user-status" value={value.status} onChange={event => setValue({ ...value, status: event.target.value as UserWrite['status'] })}>
            <option>Active</option>
            <option>Inactive</option>
          </select>
        </div>
        <FormField id="user-manager" label="Manager name" maxLength={200} value={value.managerName || ''}
          onChange={event => setValue({ ...value, managerName: event.target.value || null })} />
        <label>
          <input type="checkbox" checked={value.vendorIndicator} onChange={event => setValue({ ...value, vendorIndicator: event.target.checked })} />
          {' '}Vendor
        </label>
        {error && <p role="alert" className="error">{error}</p>}
        <div className="actions">
          <Button type="submit" pending={pending}>{pending ? 'Saving…' : 'Save user'}</Button>
          <Button type="button" variant="secondary" disabled={pending} onClick={onCancel}>Cancel</Button>
        </div>
      </fieldset>
    </form>
  );
}
