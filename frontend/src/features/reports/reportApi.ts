/** Read and export scoped inventory reports using the session bearer. */
import { api, ApiError, SESSION_EXPIRED, TOKEN_KEY } from '../../shared/api';
import type { Application, ListPage, Portfolio, User } from '../../types';

export type ReportKind = 'applications' | 'portfolios';
/** Respect both editable permissions and immutable read-only restrictions. */
export function canReport(user: User | null, exportRequested = false): boolean {
  return !!user && !user.mustChangePassword && user.permissions.includes('view') &&
    (!exportRequested || (user.role !== 'Read Only' && user.permissions.includes('export')));
}
/** Read one bounded report page. */
export function listReport(kind: 'applications', query: string): Promise<ListPage<Application>>;
export function listReport(kind: 'portfolios', query: string): Promise<ListPage<Portfolio>>;
export function listReport(kind: ReportKind, query: string): Promise<ListPage<Application> | ListPage<Portfolio>> {
  return api(`/reports/${kind}${query ? `?${query}` : ''}`);
}
/** Download all rows matching applied filters, regardless of the visible page. */
export async function downloadReport(kind: ReportKind, query: string): Promise<void> {
  const params = new URLSearchParams(query);
  params.delete('report');
  params.set('format', 'csv');
  const headers = new Headers();
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  let response: Response;
  try { response = await fetch(`${import.meta.env.VITE_API_BASE_URL || '/api'}/reports/${kind}?${params}`, { headers }); }
  catch { throw new ApiError(0, 'Unable to reach the service. Please try again.'); }
  if (!response.ok) {
    if (response.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      window.dispatchEvent(new Event(SESSION_EXPIRED));
    }
    let detail: unknown;
    try { detail = (await response.json()).detail; } catch { detail = undefined; }
    throw new ApiError(response.status, typeof detail === 'string' ? detail : 'Unable to export report.');
  }
  const url = URL.createObjectURL(await response.blob());
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = `${kind}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally { URL.revokeObjectURL(url); }
}
