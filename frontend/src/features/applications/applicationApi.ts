/** Consume application reads through the shared bearer boundary. */
import { api, ApiError } from '../../shared/api';
import type { Application, ListPage, User } from '../../types';

/** Respect the effective view permission and mandatory password change. */
export function canViewApplications(user: User | null): boolean {
  return Boolean(user && !user.mustChangePassword && user.permissions.includes('view'));
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
