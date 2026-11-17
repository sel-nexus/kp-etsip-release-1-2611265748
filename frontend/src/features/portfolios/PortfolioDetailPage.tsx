/** Display scoped portfolio metadata, maintenance actions and real linked inventory. */
import { useCallback, useState } from 'react';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { useResource } from '../../shared/useResource';
import { Button } from '../../shared/Button';
import { ConfirmDialog } from '../../shared/ConfirmDialog';
import { DataTable } from '../../shared/DataTable';
import { canPortfolio, deletePortfolio, getPortfolio, linkedApplications, savePortfolio } from './portfolioApi';
import PortfolioForm from './PortfolioForm';
/** Offer edits only within immutable role and assignment boundaries. */
export default function PortfolioDetailPage() {
  const { id = '' } = useParams();
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [message, setMessage] = useState((location.state as { message?: string } | null)?.message || '');
  const [confirm, setConfirm] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const load = useCallback(() => getPortfolio(id), [id]);
  const detail = useResource(load, canPortfolio(user, 'view'));
  const page = Number(params.get('applicationsPage') || '1');
  const loadApps = useCallback(() => linkedApplications(id, page), [id, page]);
  const applications = useResource(loadApps, Boolean(detail.data));
  const editing = params.get('mode') === 'edit' && canPortfolio(user, 'edit', id);
  /** Retain linked pagination while navigating edit mode. */
  function mode(value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set('mode', value); else next.delete('mode');
    setParams(next);
  }
  /** Delete only after explicit confirmation and retain the dialog on conflicts. */
  async function remove() {
    setPending(true);
    setError('');
    try {
      await deletePortfolio(id);
      navigate('/portfolios', { state: { message: 'Portfolio deleted.' } });
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to delete portfolio.'); }
    finally { setPending(false); }
  }
  const row = detail.data;
  return (
    <>
      <p><Link to="/portfolios">Back to portfolios</Link></p>
      {!canPortfolio(user, 'view') && <p role="alert" className="error">Access denied</p>}
      {detail.loading && <p role="status">Loading portfolio…</p>}
      {detail.error && (
        <div>
          <p role="alert" className="error">{detail.error}</p>
          <Button variant="secondary" onClick={detail.retry}>Retry portfolio</Button>
        </div>
      )}
      {row && (
        <>
          <h1>{row.name}</h1>
          {message && <p role="status" className="notice">{message}</p>}
          {editing ? <PortfolioForm key={row.id} initial={row} onCancel={() => mode('')} onSave={async payload => {
            await savePortfolio(payload, id);
            mode('');
            setMessage('Portfolio saved.');
            detail.retry();
          }} /> : (
            <>
              <section className="card" aria-label="Portfolio details">
                <dl>
                  <dt>Owner</dt><dd>{row.owner || '—'}</dd>
                  <dt>Description</dt><dd>{row.description || '—'}</dd>
                  <dt>Product area</dt><dd>{row.productArea || '—'}</dd>
                  <dt>Status</dt><dd>{row.status}</dd>
                  <dt>Applications</dt><dd>{row.applicationCount}</dd>
                  <dt>Quality score</dt><dd>{row.qualityScore ?? 'N/A'}</dd>
                  <dt>Created</dt><dd>{new Date(row.createdAt).toLocaleString()}</dd>
                  <dt>Updated</dt><dd>{new Date(row.updatedAt).toLocaleString()}</dd>
                </dl>
              </section>
              <div className="actions">
                {canPortfolio(user, 'edit', id) && <Button onClick={() => mode('edit')}>Edit portfolio</Button>}
                {canPortfolio(user, 'delete', id) && <Button variant="secondary" onClick={() => setConfirm(true)}>Delete portfolio</Button>}
              </div>
            </>
          )}
          <h2>Linked applications</h2>
          <p className="muted">Quality scores are maintained inventory values, not automated test evidence.</p>
          {applications.loading && <p role="status">Loading linked applications…</p>}
          {applications.error && (
            <div>
              <p role="alert" className="error">{applications.error}</p>
              <Button variant="secondary" onClick={applications.retry}>Retry applications</Button>
            </div>
          )}
          {applications.data && <DataTable caption="Linked applications" data={applications.data}
            emptyMessage="No linked applications."
            onPage={value => {
              const next = new URLSearchParams(params);
              next.set('applicationsPage', String(value));
              setParams(next);
            }} columns={[
              { title: 'Name', render: app => <Link to={`/applications/${app.id}`}>{app.name}</Link> },
              { title: 'Product area', render: app => app.productArea },
              { title: 'Lifecycle', render: app => app.lifecycleStatus },
              { title: 'Quality score', render: app => app.qualityScore },
              { title: 'Risk', render: app => app.riskLevel },
            ]} />}
        </>
      )}
      {confirm && <ConfirmDialog title="Delete portfolio?" message="This permanently removes the portfolio. Linked applications prevent deletion."
        pending={pending} error={error} onCancel={() => setConfirm(false)} onConfirm={() => void remove()} />}
    </>
  );
}
