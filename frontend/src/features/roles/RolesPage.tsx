/** Provide accessible editing for the six fixed roles. */
import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import type { Permission, Role } from '../../types';
import { Button } from '../../shared/Button';
import { useResource } from '../../shared/useResource';
import { useAuth } from '../auth/AuthProvider';
import { canAdminister } from '../users/userApi';
import { listRoles, saveRole } from './roleApi';

const permissions: Permission[] = ['view', 'create', 'edit', 'delete', 'export', 'administer'];

/** Show the role list and an explicit, labeled permission editor. */
export default function RolesPage() {
  const { user, refresh } = useAuth();
  const allowed = canAdminister(user);
  const load = useCallback(() => listRoles(), []);
  const roles = useResource(load, allowed);
  const [selected, setSelected] = useState<Role | null>(null);
  const [description, setDescription] = useState('');
  const [checked, setChecked] = useState<Permission[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  /** Populate the editor from the selected persisted role. */
  function select(role: Role) {
    setSelected(role);
    setDescription(role.description);
    setChecked(role.permissions);
    setError('');
    setMessage('');
  }
  /** Save the selected record and refresh identity and the listing. */
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setPending(true);
    setError('');
    setMessage('');
    try {
      const saved = await saveRole(selected.id, { description, permissions: checked });
      setSelected(saved);
      setMessage('Role saved.');
      roles.retry();
      if (saved.name === user?.role) await refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Unable to save role.');
    } finally {
      setPending(false);
    }
  }
  return (
    <>
      <h1>Administration</h1>
      <nav aria-label="Administration sections">
        <Link to="/administration">Users</Link>{' · '}
        <span aria-current="page">Roles</span>
      </nav>
      {!allowed ? <p role="alert" className="error">Access denied</p> : (
        <>
          <h2>Roles</h2>
          <p className="muted">Edit generic permissions. Fixed role restrictions and user assignments still apply.</p>
          {roles.loading && <p role="status">Loading roles…</p>}
          {roles.error && (
            <div>
              <p role="alert" className="error">{roles.error}</p>
              <Button onClick={roles.retry}>Retry roles</Button>
            </div>
          )}
          {roles.data && roles.data.items.length === 0 && <p>No roles available.</p>}
          {roles.data && (
            <ul>
              {roles.data.items.map(role => (
                <li key={role.id}>
                  <Button variant="secondary" onClick={() => select(role)}>Edit {role.name}</Button>
                </li>
              ))}
            </ul>
          )}
          {selected && (
            <form aria-label="Role editor" className="card" onSubmit={event => void submit(event)}>
              <h3>{selected.name}</h3>
              <div className="field">
                <label htmlFor="role-description">Description</label>
                <textarea id="role-description" maxLength={500} value={description} onChange={event => setDescription(event.target.value)} />
              </div>
              <fieldset>
                <legend>Generic permissions</legend>
                {permissions.map(permission => (
                  <div key={permission}>
                    <label>
                      <input type="checkbox" checked={checked.includes(permission)} onChange={event => setChecked(
                        event.target.checked ? [...checked, permission] : checked.filter(value => value !== permission)
                      )} />{' '}
                      {permission}
                    </label>
                  </div>
                ))}
              </fieldset>
              {error && <p role="alert" className="error">{error}</p>}
              {message && <p role="status" className="notice">{message}</p>}
              <Button type="submit" pending={pending}>{pending ? 'Saving…' : 'Save role'}</Button>
            </form>
          )}
        </>
      )}
    </>
  );
}
