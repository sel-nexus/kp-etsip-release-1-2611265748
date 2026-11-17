/** Inspect an accessible, URL-filtered audit trail. */
import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { Button } from '../../shared/Button';
import { DataTable } from '../../shared/DataTable';
import { useResource } from '../../shared/useResource';
import { canAudit, downloadAudit, listAudit } from './auditApi';

const actions = ['login', 'create', 'edit', 'delete', 'roleChange', 'permissionChange', 'export'];

/** Render filters, bounded results, and permission-gated export. */
export default function AuditPage() {
  const { user } = useAuth();
  const allowed = canAudit(user, 'view');
  const [params, setParams] = useSearchParams();
  const query = params.toString();
  const [userId, setUserId] = useState(params.get('userId') || '');
  const [action, setAction] = useState(params.get('action') || '');
  const [from, setFrom] = useState(params.get('from') || '');
  const [to, setTo] = useState(params.get('to') || '');
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    setUserId(params.get('userId') || '');
    setAction(params.get('action') || '');
    setFrom(params.get('from') || '');
    setTo(params.get('to') || '');
  }, [query]);
  const load = useCallback(() => listAudit(query), [query]);
  const resource = useResource(load, allowed);
  /** Export the applied filters, not unapplied form values. */
  async function download() {
    setExporting(true);
    setError('');
    try { await downloadAudit(query); resource.retry(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to export audit logs.'); }
    finally { setExporting(false); }
  }
  return (
    <>
      <h1>Audit</h1>
      {!allowed ? <p role="alert" className="error">Access denied</p> : (
        <>
          <p className="muted">Review sensitive activity. Date and time filters must use UTC.</p>
          <form className="filters" aria-label="Audit filters" onSubmit={event => {
            event.preventDefault();
            const next = new URLSearchParams();
            for (const [key, value] of Object.entries({ userId: userId.trim(), action, from: from.trim(), to: to.trim() })) {
              if (value) next.set(key, value);
            }
            next.set('page', '1');
            setParams(next);
          }}>
            <div className="field">
              <label htmlFor="audit-user">User ID</label>
              <input id="audit-user" maxLength={24} value={userId} onChange={event => setUserId(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="audit-action">Action</label>
              <select id="audit-action" value={action} onChange={event => setAction(event.target.value)}>
                <option value="">All actions</option>
                {actions.map(value => <option key={value} value={value}>{value}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="audit-from">From UTC</label>
              <input id="audit-from" maxLength={40} placeholder="2025-01-01T00:00:00Z" value={from} onChange={event => setFrom(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="audit-to">To UTC</label>
              <input id="audit-to" maxLength={40} placeholder="2025-12-31T23:59:59Z" value={to} onChange={event => setTo(event.target.value)} />
            </div>
            <Button type="submit" variant="secondary">Apply filters</Button>
            <Button type="button" variant="secondary" onClick={() => setParams({})}>Clear filters</Button>
          </form>
          {canAudit(user, 'export') && <Button onClick={() => void download()} pending={exporting}>{exporting ? 'Exporting…' : 'Export CSV'}</Button>}
          {error && <p role="alert" className="error">{error}</p>}
          {resource.loading && <p role="status">Loading audit logs…</p>}
          {resource.error && (
            <div>
              <p role="alert" className="error">{resource.error}</p>
              <Button variant="secondary" onClick={resource.retry}>Retry audit logs</Button>
            </div>
          )}
          {resource.data && <DataTable caption="Audit logs" data={resource.data}
            emptyMessage={query ? 'No audit events match these filters.' : 'No audit events.'}
            onPage={page => { const next = new URLSearchParams(params); next.set('page', String(page)); setParams(next); }}
            columns={[
              { title: 'UTC timestamp', render: row => row.timestamp },
              { title: 'User', render: row => row.userName },
              { title: 'User ID', render: row => row.userId || '—' },
              { title: 'Action', render: row => row.action },
              { title: 'Entity', render: row => `${row.entityType}${row.entityId ? ` · ${row.entityId}` : ''}` },
              { title: 'Details', render: row => row.details },
            ]} />}
        </>
      )}
    </>
  );
}
