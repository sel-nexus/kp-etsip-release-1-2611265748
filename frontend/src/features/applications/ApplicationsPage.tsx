/** Present a searchable, URL-addressable application inventory. */
import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { listPortfolios } from '../portfolios/portfolioApi';
import { Button } from '../../shared/Button';
import { DataTable } from '../../shared/DataTable';
import { useResource } from '../../shared/useResource';
import { canViewApplications, listApplications } from './applicationApi';

/** Display user-visible results, filters, pagination, and recoverable failures. */
export default function ApplicationsPage() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const query = params.toString();
  const allowed = canViewApplications(user);
  const [search, setSearch] = useState(params.get('search') || '');
  const [portfolio, setPortfolio] = useState(params.get('portfolioId') || '');
  const [criticality, setCriticality] = useState(params.get('criticality') || '');
  const [risk, setRisk] = useState(params.get('riskLevel') || '');
  const [lifecycle, setLifecycle] = useState(params.get('lifecycleStatus') || '');
  useEffect(() => {
    setSearch(params.get('search') || '');
    setPortfolio(params.get('portfolioId') || '');
    setCriticality(params.get('criticality') || '');
    setRisk(params.get('riskLevel') || '');
    setLifecycle(params.get('lifecycleStatus') || '');
  }, [query]);
  const load = useCallback(() => listApplications(query), [query]);
  const loadPortfolios = useCallback(() => listPortfolios('pageSize=100'), []);
  const resource = useResource(load, allowed);
  const portfolios = useResource(loadPortfolios, allowed);
  return (
    <>
      <h1>Applications</h1>
      <p className="muted">Quality and risk values are manually maintained inventory, not automated evidence.</p>
      {!allowed ? <p role="alert" className="error">Access denied</p> : (
        <>
          <form className="filters" aria-label="Application filters" onSubmit={event => {
            event.preventDefault();
            const next = new URLSearchParams();
            for (const [key, value] of Object.entries({ search: search.trim(), portfolioId: portfolio, criticality, riskLevel: risk, lifecycleStatus: lifecycle })) {
              if (value) next.set(key, value);
            }
            next.set('page', '1');
            next.set('pageSize', params.get('pageSize') || '25');
            setParams(next);
          }}>
            <div className="field">
              <label htmlFor="app-search">Search applications</label>
              <input id="app-search" maxLength={200} value={search} onChange={event => setSearch(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="app-portfolio">Portfolio filter</label>
              <select id="app-portfolio" value={portfolio} onChange={event => setPortfolio(event.target.value)}>
                <option value="">All portfolios</option>
                {portfolios.data?.items.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </div>
            {portfolios.error && <p role="alert">Unable to load portfolio choices. <Button type="button" variant="secondary" onClick={portfolios.retry}>Retry portfolios</Button></p>}
            <div className="field">
              <label htmlFor="app-criticality">Criticality filter</label>
              <select id="app-criticality" value={criticality} onChange={event => setCriticality(event.target.value)}>
                <option value="">All criticalities</option>
                {['Low', 'Medium', 'High', 'Critical'].map(value => <option key={value}>{value}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="app-risk">Risk level filter</label>
              <select id="app-risk" value={risk} onChange={event => setRisk(event.target.value)}>
                <option value="">All risk levels</option>
                {['Low', 'Medium', 'High'].map(value => <option key={value}>{value}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="app-lifecycle">Lifecycle status filter</label>
              <select id="app-lifecycle" value={lifecycle} onChange={event => setLifecycle(event.target.value)}>
                <option value="">All lifecycle statuses</option>
                {['Active', 'Deprecated', 'Retired'].map(value => <option key={value}>{value}</option>)}
              </select>
            </div>
            <Button type="submit" variant="secondary">Apply filters</Button>
            <Button type="button" variant="secondary" onClick={() => setParams({})}>Clear filters</Button>
          </form>
          {resource.loading && <p role="status">Loading applications…</p>}
          {resource.error && <div><p role="alert" className="error">{resource.error}</p><Button variant="secondary" onClick={resource.retry}>Retry applications</Button></div>}
          {resource.data && <DataTable caption="Application inventory" data={resource.data}
            emptyMessage={query ? 'No applications match these filters.' : 'No visible applications.'}
            onPage={page => { const next = new URLSearchParams(params); next.set('page', String(page)); setParams(next); }}
            columns={[
              { title: 'Name', render: row => <Link to={`/applications/${row.id}`}>{row.name}</Link> },
              { title: 'Portfolio', render: row => <Link to={`/portfolios/${row.portfolioId}`}>{row.portfolioName}</Link> },
              { title: 'Criticality', render: row => row.criticality },
              { title: 'Tier', render: row => row.tier },
              { title: 'Lifecycle status', render: row => row.lifecycleStatus },
              { title: 'Health score', render: row => row.applicationHealthScore },
              { title: 'Automation coverage %', render: row => row.automationCoverage },
              { title: 'Open critical defects', render: row => row.openCriticalDefects },
              { title: 'Risk level', render: row => row.riskLevel },
            ]} />}
        </>
      )}
    </>
  );
}
