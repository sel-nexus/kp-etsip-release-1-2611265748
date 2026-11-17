/** Display every maintained application field without providing write actions. */
import { useCallback, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { Button } from '../../shared/Button';
import { ConfirmDialog } from '../../shared/ConfirmDialog';
import { useResource } from '../../shared/useResource';
import { canViewApplications, canWriteApplication, deleteApplication, getApplication, safeWebLink } from './applicationApi';

/** Offer safe external links and scoped portfolio navigation. */
export default function ApplicationDetailPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [confirm, setConfirm] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const { user } = useAuth();
  const allowed = canViewApplications(user);
  const load = useCallback(() => getApplication(id), [id]);
  const resource = useResource(load, allowed);
  const item = resource.data;
  const repository = safeWebLink(item?.repositoryLink || null);
  const pipeline = safeWebLink(item?.pipelineLink || null);
  return (
    <>
      <p><Link to="/applications">Back to applications</Link></p>
      {!allowed && <p role="alert" className="error">Access denied</p>}
      {resource.loading && <p role="status">Loading application…</p>}
      {resource.error && <div><p role="alert" className="error">{resource.error}</p><Button variant="secondary" onClick={resource.retry}>Retry application</Button></div>}
      {item && (
        <>
          <h1>{item.name}</h1>
          {(location.state as { message?: string } | null)?.message && <p role="status">{(location.state as { message: string }).message}</p>}
          <p className="muted">These quality and risk values are manually maintained.</p>
          <div className="actions">
            {canWriteApplication(user, 'edit') && <Link to={`/applications/${id}/edit`}>Edit application</Link>}
            {canWriteApplication(user, 'delete') && <Button variant="secondary" onClick={() => setConfirm(true)}>Delete application</Button>}
          </div>
          <section className="card" aria-label="Application details">
            <dl>
              <dt>Description</dt><dd>{item.description || '—'}</dd>
              <dt>Portfolio</dt><dd><Link to={`/portfolios/${item.portfolioId}`}>{item.portfolioName}</Link></dd>
              <dt>Product area</dt><dd>{item.productArea || '—'}</dd>
              <dt>Business owner</dt><dd>{item.businessOwner || '—'}</dd>
              <dt>Technology owner</dt><dd>{item.technologyOwner || '—'}</dd>
              <dt>ETS owner</dt><dd>{item.etsOwner || '—'}</dd>
              <dt>Criticality</dt><dd>{item.criticality}</dd>
              <dt>Tier</dt><dd>{item.tier}</dd>
              <dt>Lifecycle status</dt><dd>{item.lifecycleStatus}</dd>
              <dt>Technology stack</dt><dd>{item.technologyStack || '—'}</dd>
              <dt>Health score</dt><dd>{item.applicationHealthScore}</dd>
              <dt>Quality score</dt><dd>{item.qualityScore}</dd>
              <dt>Automation coverage</dt><dd>{item.automationCoverage}%</dd>
              <dt>Unit-test coverage</dt><dd>{item.unitTestCoverage}%</dd>
              <dt>Open defects</dt><dd>{item.openDefects}</dd>
              <dt>Open critical defects</dt><dd>{item.openCriticalDefects}</dd>
              <dt>Risk level</dt><dd>{item.riskLevel}</dd>
              <dt>Repository</dt><dd>{repository ? <a href={repository} target="_blank" rel="noopener noreferrer">Open repository</a> : 'Not available'}</dd>
              <dt>Pipeline</dt><dd>{pipeline ? <a href={pipeline} target="_blank" rel="noopener noreferrer">Open pipeline</a> : 'Not available'}</dd>
              <dt>Created</dt><dd>{new Date(item.createdAt).toLocaleString()}</dd>
              <dt>Updated</dt><dd>{new Date(item.updatedAt).toLocaleString()}</dd>
            </dl>
          </section>
        </>
      )}
      {confirm && <ConfirmDialog title="Delete application?" message="This permanently removes the application." pending={pending} error={error}
        onCancel={() => setConfirm(false)} onConfirm={() => {
          setPending(true); setError('');
          void deleteApplication(id).then(() => navigate('/applications', { state: { message: 'Application deleted.' } }))
            .catch(failure => setError(failure instanceof Error ? failure.message : 'Unable to delete application.'))
            .finally(() => setPending(false));
        }} />}
    </>
  );
}
