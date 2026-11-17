/** Display shareable, scoped inventory report tables. */
import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { Button } from '../../shared/Button';
import { DataTable } from '../../shared/DataTable';
import { useResource } from '../../shared/useResource';
import { canReport, downloadReport, listReport } from './reportApi';

/** Render both navigable reports with filters and export feedback. */
export default function ReportsPage() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const kind = params.get('report') === 'portfolios' ? 'portfolios' : 'applications';
  const query = params.toString();
  const [search, setSearch] = useState(params.get('search') || '');
  const [portfolioId, setPortfolioId] = useState(params.get('portfolioId') || '');
  const [criticality, setCriticality] = useState(params.get('criticality') || '');
  const [riskLevel, setRiskLevel] = useState(params.get('riskLevel') || '');
  const [lifecycleStatus, setLifecycleStatus] = useState(params.get('lifecycleStatus') || '');
  const [status, setStatus] = useState(params.get('status') || '');
  const [productArea, setProductArea] = useState(params.get('productArea') || '');
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  useEffect(() => {
    setSearch(params.get('search') || '');
    setPortfolioId(params.get('portfolioId') || '');
    setCriticality(params.get('criticality') || '');
    setRiskLevel(params.get('riskLevel') || '');
    setLifecycleStatus(params.get('lifecycleStatus') || '');
    setStatus(params.get('status') || '');
    setProductArea(params.get('productArea') || '');
  }, [query]);
  const apiQuery = new URLSearchParams(query);
  apiQuery.delete('report');
  const requestQuery = apiQuery.toString();
  const allowed = canReport(user);
  const loadApps = useCallback(() => listReport('applications', requestQuery), [requestQuery]);
  const loadPortfolios = useCallback(() => listReport('portfolios', requestQuery), [requestQuery]);
  const apps = useResource(loadApps, allowed && kind === 'applications');
  const portfolios = useResource(loadPortfolios, allowed && kind === 'portfolios');
  const active = kind === 'applications' ? apps : portfolios;
  /** Send applied URL filters rather than unsaved form fields. */
  async function download() {
    setExporting(true);
    setExportError('');
    try { await downloadReport(kind, requestQuery); }
    catch (failure) { setExportError(failure instanceof Error ? failure.message : 'Unable to export report.'); }
    finally { setExporting(false); }
  }
  /** Retain applied filters when changing pages. */
  function changePage(page: number) {
    const next = new URLSearchParams(params);
    next.set('page', String(page));
    setParams(next);
  }
  return (
    <>
      <h1>Reports</h1>
      {!allowed ? <p role="alert" className="error">Access denied</p> : (
        <>
          <p className="muted">Report values come from manually maintained inventory.</p>
          <nav className="actions" aria-label="Report selection">
            <Link to="/reports?report=applications" aria-current={kind === 'applications' ? 'page' : undefined}>Application Report</Link>
            <Link to="/reports?report=portfolios" aria-current={kind === 'portfolios' ? 'page' : undefined}>Portfolio Report</Link>
          </nav>
          <form className="filters" aria-label="Report filters" onSubmit={event => {
            event.preventDefault();
            const next = new URLSearchParams({ report: kind, page: '1', pageSize: params.get('pageSize') || '25' });
            const values = kind === 'applications' ? { search: search.trim(), portfolioId, criticality, riskLevel, lifecycleStatus } : { search: search.trim(), status, productArea };
            for (const [key, value] of Object.entries(values)) if (value) next.set(key, value);
            setParams(next);
          }}>
            <div className="field">
              <label htmlFor="report-search">Search</label>
              <input id="report-search" maxLength={200} value={search} onChange={event => setSearch(event.target.value)} />
            </div>
            {kind === 'applications' ? (
              <>
                <div className="field">
                  <label htmlFor="report-portfolio">Portfolio ID</label>
                  <input id="report-portfolio" maxLength={24} value={portfolioId} onChange={event => setPortfolioId(event.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="report-criticality">Criticality</label>
                  <select id="report-criticality" value={criticality} onChange={event => setCriticality(event.target.value)}>
                    <option value="">All</option>
                    {['Low', 'Medium', 'High', 'Critical'].map(value => <option key={value}>{value}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="report-risk">Risk level</label>
                  <select id="report-risk" value={riskLevel} onChange={event => setRiskLevel(event.target.value)}>
                    <option value="">All</option>
                    {['Low', 'Medium', 'High'].map(value => <option key={value}>{value}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="report-lifecycle">Lifecycle status</label>
                  <select id="report-lifecycle" value={lifecycleStatus} onChange={event => setLifecycleStatus(event.target.value)}>
                    <option value="">All</option>
                    {['Active', 'Deprecated', 'Retired'].map(value => <option key={value}>{value}</option>)}
                  </select>
                </div>
              </>
            ) : (
              <>
                <div className="field">
                  <label htmlFor="report-area">Product area</label>
                  <input id="report-area" maxLength={200} value={productArea} onChange={event => setProductArea(event.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="report-status">Status</label>
                  <select id="report-status" value={status} onChange={event => setStatus(event.target.value)}>
                    <option value="">All</option>
                    <option>Active</option>
                    <option>Archived</option>
                  </select>
                </div>
              </>
            )}
            <Button type="submit" variant="secondary">Apply filters</Button>
            <Button type="button" variant="secondary" onClick={() => setParams({ report: kind })}>Clear filters</Button>
          </form>
          {canReport(user, true) && <Button onClick={() => void download()} pending={exporting}>{exporting ? 'Exporting…' : 'Export CSV'}</Button>}
          {exportError && <p role="alert" className="error">{exportError}</p>}
          {active.loading && <p role="status">Loading report…</p>}
          {active.error && <div><p role="alert" className="error">{active.error}</p><Button variant="secondary" onClick={active.retry}>Retry report</Button></div>}
          {kind === 'applications' && apps.data && <DataTable caption="Application Report" data={apps.data} onPage={changePage} emptyMessage="No applications match this report."
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
          {kind === 'portfolios' && portfolios.data && <DataTable caption="Portfolio Report" data={portfolios.data} onPage={changePage} emptyMessage="No portfolios match this report."
            columns={[
              { title: 'Name', render: row => <Link to={`/portfolios/${row.id}`}>{row.name}</Link> },
              { title: 'Owner', render: row => row.owner || '—' },
              { title: 'Product area', render: row => row.productArea || '—' },
              { title: 'Applications', render: row => row.applicationCount },
              { title: 'Quality score', render: row => row.qualityScore ?? 'N/A' },
              { title: 'Status', render: row => row.status },
            ]} />}
        </>
      )}
    </>
  );
}
