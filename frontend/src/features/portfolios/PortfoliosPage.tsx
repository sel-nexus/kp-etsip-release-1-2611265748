/** Present URL-shareable portfolio inventory and authorized creation. */
import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { Button } from '../../shared/Button';
import { DataTable } from '../../shared/DataTable';
import { useResource } from '../../shared/useResource';
import { canPortfolio, listPortfolios, savePortfolio } from './portfolioApi';
import PortfolioForm from './PortfolioForm';
/** Load only the current URL query and expose deliberate create/filter actions. */
export default function PortfoliosPage() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [search, setSearch] = useState(params.get('search') || '');
  const [area, setArea] = useState(params.get('productArea') || '');
  const [status, setStatus] = useState(params.get('status') || '');
  const query = params.toString();
  const allowed = canPortfolio(user, 'view');
  const load = useCallback(() => listPortfolios(query), [query]);
  const resource = useResource(load, allowed);
  useEffect(() => {
    setSearch(params.get('search') || '');
    setArea(params.get('productArea') || '');
    setStatus(params.get('status') || '');
  }, [query]);
  const creating = params.get('form') === 'new' && canPortfolio(user, 'create');
  /** Preserve filters while changing a single navigable control. */
  function change(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next);
  }
  return (
    <>
      <h1>Portfolios</h1>
      <p className="muted">Maintain portfolio ownership and view quality derived from linked application inventory.</p>
      {(location.state as { message?: string } | null)?.message && (
        <p role="status" className="notice">{(location.state as { message: string }).message}</p>
      )}
      {!allowed ? <p role="alert" className="error">Access denied</p> : (
        <>
          <form className="filters" aria-label="Portfolio filters" onSubmit={event => {
            event.preventDefault();
            const next = new URLSearchParams();
            if (search.trim()) next.set('search', search.trim());
            if (area) next.set('productArea', area);
            if (status) next.set('status', status);
            next.set('page', '1');
            next.set('pageSize', params.get('pageSize') || '25');
            setParams(next);
          }}>
            <div className="field">
              <label htmlFor="portfolio-search">Search portfolios</label>
              <input id="portfolio-search" value={search} maxLength={200} onChange={event => setSearch(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="area-filter">Product area filter</label>
              <input id="area-filter" value={area} maxLength={200} onChange={event => setArea(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="status-filter">Status filter</label>
              <select id="status-filter" value={status} onChange={event => setStatus(event.target.value)}>
                <option value="">All statuses</option>
                <option>Active</option>
                <option>Archived</option>
              </select>
            </div>
            <Button type="submit" variant="secondary">Apply filters</Button>
            <Button type="button" variant="secondary" onClick={() => setParams({})}>Clear filters</Button>
          </form>
          {canPortfolio(user, 'create') && !creating && <Button onClick={() => change('form', 'new')}>Create portfolio</Button>}
          {creating && <PortfolioForm onCancel={() => change('form', '')} onSave={async payload => {
            const saved = await savePortfolio(payload);
            navigate(`/portfolios/${saved.id}`, { state: { message: 'Portfolio created.' } });
          }} />}
          {resource.loading && <p role="status">Loading portfolios…</p>}
          {resource.error && (
            <div>
              <p role="alert" className="error">{resource.error}</p>
              <Button variant="secondary" onClick={resource.retry}>Retry portfolios</Button>
            </div>
          )}
          {resource.data && <DataTable caption="Portfolio inventory" data={resource.data}
            onPage={page => change('page', String(page))}
            emptyMessage={search || status || area ? 'No portfolios match these filters.' : 'No visible portfolios.'}
            columns={[
              { title: 'Name', render: row => <Link to={`/portfolios/${row.id}`}>{row.name}</Link> },
              { title: 'Owner', render: row => row.owner || '—' },
              { title: 'Product area', render: row => row.productArea || '—' },
              { title: 'Status', render: row => row.status },
              { title: 'Applications', render: row => row.applicationCount },
              { title: 'Quality score', render: row => row.qualityScore ?? 'N/A' },
            ]} />}
        </>
      )}
    </>
  );
}
