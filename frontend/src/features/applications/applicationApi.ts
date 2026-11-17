/** Consume application reads through the shared bearer boundary. */
import { api, ApiError } from '../../shared/api';
import type { Application, ApplicationWrite, ListPage, User } from '../../types';

/** Respect the effective view permission and mandatory password change. */
export function canViewApplications(user: User | null): boolean {
  return Boolean(user && !user.mustChangePassword && user.permissions.includes('view'));
}

/** Honor immutable role boundaries and effective permissions. */
export function canWriteApplication(user: User | null, action: 'create' | 'edit' | 'delete'): boolean {
  return Boolean(canViewApplications(user) && user?.permissions.includes(action) &&
    (action === 'delete' ? user.role === 'Administrator' : ['Administrator', 'Portfolio Leader', 'Engineer'].includes(user.role)));
}

/** Save validated inventory through the authenticated API. */
export function saveApplication(value: ApplicationWrite, id?: string): Promise<Application> {
  return api<Application>(id ? `/applications/${encodeURIComponent(id)}` : '/applications', {
    method: id ? 'PUT' : 'POST', body: JSON.stringify(value),
  });
}

/** Permanently remove an application after confirmation. */
export function deleteApplication(id: string): Promise<void> {
  return api<void>(`/applications/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

/** Fetch a typed inventory page using URL-selected filters. */
export async function listApplications(query: string): Promise<ListPage<Application>> {
  try { return await api<ListPage<Application>>(`/applications?${query}`); }
  catch (error) {
    if (error instanceof ApiError && error.status === 422) throw new ApiError(422, 'Check the application filters.');
    throw error;
  }
}

/** Fetch a visible application and its current portfolio name. */
export function getApplication(id: string): Promise<Application> {
  return api<Application>(`/applications/${encodeURIComponent(id)}`);
}

/** Permit only absolute HTTP(S) links without embedded credentials. */
export function safeWebLink(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}
