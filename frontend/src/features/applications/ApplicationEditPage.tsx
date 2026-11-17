/** Coordinate creation and editing using scoped portfolio choices. */
import { useCallback } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { listPortfolios } from '../portfolios/portfolioApi';
import { useResource } from '../../shared/useResource';
import { Button } from '../../shared/Button';
import { canWriteApplication, getApplication, saveApplication } from './applicationApi';
import ApplicationForm from './ApplicationForm';

/** Load the current record and selectable portfolios before presenting the form. */
export default function ApplicationEditPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const allowed = canWriteApplication(user, id ? 'edit' : 'create');
  const load = useCallback(() => getApplication(id || ''), [id]);
  const loadPortfolios = useCallback(async () => {
    const first = await listPortfolios('pageSize=100');
    const items = [...first.items];
    for (let page = 2; items.length < first.total; page += 1) {
      const next = await listPortfolios(`pageSize=100&page=${page}`);
      if (!next.items.length) break;
      items.push(...next.items);
    }
    return { ...first, items };
  }, []);
  const item = useResource(load, allowed && Boolean(id));
  const portfolios = useResource(loadPortfolios, allowed);
  return (
    <>
      <p><Link to={id ? `/applications/${id}` : '/applications'}>Back to applications</Link></p>
      <h1>{id ? 'Edit application' : 'Create application'}</h1>
      {!allowed && <p role="alert">Access denied</p>}
      {(portfolios.loading || item.loading) && <p role="status">Loading application form…</p>}
      {portfolios.error && <div><p role="alert">{portfolios.error}</p><Button onClick={portfolios.retry}>Retry portfolios</Button></div>}
      {item.error && <div><p role="alert">{item.error}</p><Button onClick={item.retry}>Retry application</Button></div>}
      {allowed && portfolios.data && (!id || item.data) && <ApplicationForm initial={item.data || undefined} portfolios={portfolios.data.items}
        onCancel={() => navigate(id ? `/applications/${id}` : '/applications')}
        onSave={async value => { const saved = await saveApplication(value, id); navigate(`/applications/${saved.id}`, { state: { message: 'Application saved.' } }); }} />}
    </>
  );
}
