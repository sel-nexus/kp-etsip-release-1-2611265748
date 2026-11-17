/** Fetch and download audit records with the shared bearer contract. */
import { api, ApiError, SESSION_EXPIRED, TOKEN_KEY } from '../../shared/api';
import type { AuditRecord, ListPage, User } from '../../types';

/** Respect fixed role boundaries as well as live generic permissions. */
export function canAudit(user: User | null, permission: 'view' | 'export'): boolean {
  return !!user && !user.mustChangePassword && ['Administrator', 'Auditor'].includes(user.role)
    && user.permissions.includes('view') && user.permissions.includes(permission);
}

/** Read one filtered audit page. */
export function listAudit(query: string): Promise<ListPage<AuditRecord>> {
  return api<ListPage<AuditRecord>>(`/audit-logs${query ? `?${query}` : ''}`);
}

/** Download the full filtered CSV and revoke the temporary object URL. */
export async function downloadAudit(query: string): Promise<void> {
  const params = new URLSearchParams(query);
  params.set('format', 'csv');
  const headers = new Headers();
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${import.meta.env.VITE_API_BASE_URL || '/api'}/audit-logs?${params}`, { headers });
  } catch {
    throw new ApiError(0, 'Unable to reach the service. Please try again.');
  }
  if (!response.ok) {
    if (response.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      window.dispatchEvent(new Event(SESSION_EXPIRED));
    }
    let detail: unknown;
    try { detail = (await response.json()).detail; } catch { detail = undefined; }
    throw new ApiError(response.status, typeof detail === 'string' ? detail : 'Unable to export audit logs.');
  }
  const url = URL.createObjectURL(await response.blob());
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = 'audit-logs.csv';
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
