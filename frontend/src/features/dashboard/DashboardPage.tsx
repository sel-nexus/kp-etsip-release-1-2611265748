/** Present scoped, manually maintained executive inventory metrics. */
import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { Button } from '../../shared/Button';
import { useResource } from '../../shared/useResource';
import { getDashboard } from './dashboardApi';

/** Display URL-addressable filters and metrics with explicit empty and error states. */
export default function DashboardPage() {
  const { user } = useAuth();
  const allowed = !!user?.permissions.includes('view');
  const [params, setParams] = useSearchParams();
  const query = params.toString();
  const [portfolio, setPortfolio] = useState(params.get('portfolioId') || '');
  const [area, setArea] = useState(params.get('productArea') || '');
  const [risk, setRisk] = useState(params.get('riskLevel') || '');
  useEffect(() => {
    setPortfolio(params.get('portfolioId') || '');
    setArea(params.get('productArea') || '');
    setRisk(params.get('riskLevel') || '');
  }, [query]);
  const load = useCallback(() => getDashboard(query), [query]);
  const loadChoices = useCallback(() => getDashboard(''), []);
  const resource = useResource(load, allowed);
  const choices = useResource(loadChoices, allowed);
  const data = resource.data;
  const cards = data ? [
    ['Enterprise Quality Score', data.enterpriseQualityScore],
    ['Application Health Score', data.applicationHealthScore],
    ['Automation Maturity Score', data.automationMaturityScore],
    ['Open Critical Defects', data.openCriticalDefects],
    ['Applications at Risk', data.applicationsAtRisk],
    ['Total Applications', data.totalApplications],
    ['Total Portfolios', data.totalPortfolios],
  ] as const : [];
  return (
    <>
      <h1>Executive dashboard</h1>
      <p className="muted">Scores and defects are manually maintained application inventory, not automated evidence.</p>
      {!allowed ? <p role="alert" className="error">Access denied</p> : (
        <>
          <form className="filters" aria-label="Dashboard filters" onSubmit={event => {
            event.preventDefault();
            const next = new URLSearchParams();
            if (portfolio) next.set('portfolioId', portfolio);
            if (area.trim()) next.set('productArea', area.trim());
            if (risk) next.set('riskLevel', risk);
            setParams(next);
          }}>
            <div className="field">
              <label htmlFor="dashboard-portfolio">Portfolio filter</label>
              <select id="dashboard-portfolio" value={portfolio} onChange={event => setPortfolio(event.target.value)}>
                <option value="">All portfolios</option>
                {choices.data?.portfolios.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="dashboard-area">Product area filter</label>
              <input id="dashboard-area" maxLength={2000} value={area} onChange={event => setArea(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="dashboard-risk">Risk level filter</label>
              <select id="dashboard-risk" value={risk} onChange={event => setRisk(event.target.value)}>
                <option value="">All risk levels</option>
                {['Low', 'Medium', 'High'].map(value => <option key={value}>{value}</option>)}
              </select>
            </div>
            <Button type="submit" variant="secondary">Apply filters</Button>
            <Button type="button" variant="secondary" onClick={() => setParams({})}>Clear filters</Button>
          </form>
          {choices.error && <p role="alert">Unable to load portfolio choices. <Button variant="secondary" onClick={choices.retry}>Retry portfolios</Button></p>}
          {resource.loading && <p role="status">Loading dashboard…</p>}
          {resource.error && <div><p role="alert" className="error">{resource.error}</p><Button variant="secondary" onClick={resource.retry}>Retry dashboard</Button></div>}
          {data && (
            <>
              {data.totalApplications === 0 && <p role="status">{query ? 'No applications match these filters.' : 'No visible applications.'}</p>}
              <section aria-label="Executive metrics" className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                {cards.map(([label, value]) => (
                  <article className="card" key={label}>
                    <h2 className="text-base">{label}</h2>
                    <p className="text-3xl font-semibold tabular-nums">{value === null ? 'N/A' : value}</p>
                  </article>
                ))}
              </section>
              <section className="mt-8" aria-labelledby="portfolio-metrics">
                <h2 id="portfolio-metrics">Portfolio quality and risk</h2>
                {data.portfolios.length === 0 && <p>No visible portfolios match this selection.</p>}
                <ul className="grid gap-4 list-none p-0">
                  {data.portfolios.map(item => (
                    <li key={item.id} className="card">
                      <h3>{item.name}</h3>
                      <p>Applications: {item.applicationCount}</p>
                      <p>Quality score: {item.qualityScore === null ? 'N/A' : item.qualityScore}</p>
                      {item.qualityScore !== null && <div aria-hidden="true" className="h-2 bg-surface-container"><div className="h-2 bg-primary" style={{ width: `${item.qualityScore}%` }} /></div>}
                      <p className="mt-4">High-risk applications: {item.highRiskCount}</p>
                      {item.applicationCount > 0 && <div aria-hidden="true" className="h-2 bg-surface-container"><div className="h-2 bg-secondary" style={{ width: `${100 * item.highRiskCount / item.applicationCount}%` }} /></div>}
                    </li>
                  ))}
                </ul>
              </section>
            </>
          )}
        </>
      )}
    </>
  );
}
