/** Present the currently available Administration users tab. */
import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { Portfolio, User } from '../../types';
import { useAuth } from '../auth/AuthProvider';
import { listPortfolios } from '../portfolios/portfolioApi';
import { Button } from '../../shared/Button';
import { ConfirmDialog } from '../../shared/ConfirmDialog';
import { DataTable } from '../../shared/DataTable';
import { useResource } from '../../shared/useResource';
import { canAdminister, deactivateUser, listUsers, saveUser } from './userApi';
import UserForm from './UserForm';

/** Read all visible portfolio pages for assignment without silently truncating choices. */
async function loadPortfolios(): Promise<Portfolio[]> {
  const items: Portfolio[] = [];
  let page = 1;
  while (true) {
    const result = await listPortfolios(`page=${page}&pageSize=100`);
    items.push(...result.items);
    if (items.length >= result.total || !result.items.length) return items;
    page += 1;
  }
}

/** Manage accounts using URL-backed search and pagination. */
export default function UsersPage() {
  const { user, refresh } = useAuth();
  const allowed = canAdminister(user);
  const [params, setParams] = useSearchParams();
  const query = params.toString();
  const [search, setSearch] = useState(params.get('search') || '');
  const [editing, setEditing] = useState<User | 'new' | null>(null);
  const [deleting, setDeleting] = useState<User | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const load = useCallback(() => listUsers(query), [query]);
  const users = useResource(load, allowed);
  const portfolios = useResource(loadPortfolios, allowed && editing !== null);
  useEffect(() => setSearch(params.get('search') || ''), [query]);
  /** Preserve search while changing pages. */
  function changePage(page: number) {
    const next = new URLSearchParams(params);
    next.set('page', String(page));
    setParams(next);
  }
  /** Perform a confirmed soft deletion and refresh persisted results. */
  async function confirm() {
    if (!deleting) return;
    setPending(true);
    setError('');
    try { await deactivateUser(deleting.id); setDeleting(null); setMessage('User deactivated.'); users.retry(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to deactivate user.'); }
    finally { setPending(false); }
  }
  return (
    <>
      <h1>Administration</h1>
      <nav aria-label="Administration sections"><span aria-current="page">Users</span></nav>
      {!allowed ? <p role="alert" className="error">Access denied</p> : (
        <>
          <h2>Users</h2>
          <p className="muted">Manage local accounts, roles and portfolio access.</p>
          {message && <p role="status" className="notice">{message}</p>}
          <form className="filters" aria-label="User filters" onSubmit={event => {
            event.preventDefault();
            const next = new URLSearchParams();
            if (search.trim()) next.set('search', search.trim());
            next.set('page', '1');
            setParams(next);
          }}>
            <div className="field">
              <label htmlFor="user-search">Search users</label>
              <input id="user-search" maxLength={200} value={search} onChange={event => setSearch(event.target.value)} />
            </div>
            <Button type="submit" variant="secondary">Search</Button>
            <Button type="button" variant="secondary" onClick={() => setParams({})}>Clear</Button>
          </form>
          {!editing && <Button onClick={() => { setMessage(''); setEditing('new'); }}>Create user</Button>}
          {editing && portfolios.loading && <p role="status">Loading portfolio choices…</p>}
          {editing && portfolios.error && (
            <div>
              <p role="alert" className="error">{portfolios.error} Enter portfolio IDs manually or retry.</p>
              <Button onClick={portfolios.retry}>Retry portfolios</Button>
            </div>
          )}
          {editing && !portfolios.loading && (portfolios.data || portfolios.error) && <UserForm key={editing === 'new' ? 'new' : editing.id} initial={editing === 'new' ? undefined : editing}
            portfolios={portfolios.data || []} manualScope={Boolean(portfolios.error)} onCancel={() => setEditing(null)} onSave={async value => {
              const saved = await saveUser(value, editing === 'new' ? undefined : editing.id);
              setEditing(null);
              setMessage(editing === 'new' ? 'User created.' : 'User saved.');
              users.retry();
              if (saved.id === user?.id) await refresh();
            }} />}
          {users.loading && <p role="status">Loading users…</p>}
          {users.error && (
            <div>
              <p role="alert" className="error">{users.error}</p>
              <Button onClick={users.retry}>Retry users</Button>
            </div>
          )}
          {users.data && <DataTable caption="Users" data={users.data} onPage={changePage}
            emptyMessage={params.get('search') ? 'No users match this search.' : 'No visible users.'}
            columns={[
              { title: 'Name', render: row => row.name },
              { title: 'Email', render: row => row.email },
              { title: 'Role', render: row => row.role },
              { title: 'Status', render: row => row.status },
              { title: 'Actions', render: row => <div className="actions">
                <Button variant="secondary" onClick={() => setEditing(row)}>Edit {row.name}</Button>
                {row.status === 'Active' && row.id !== user?.id && <Button variant="secondary" onClick={() => { setError(''); setDeleting(row); }}>Deactivate {row.name}</Button>}
              </div> },
            ]} />}
          {deleting && <ConfirmDialog title="Deactivate user" message={`Deactivate ${deleting.name}? Existing sessions will be revoked.`}
            pending={pending} error={error} onCancel={() => setDeleting(null)} onConfirm={() => void confirm()} />}
        </>
      )}
    </>
  );
}
