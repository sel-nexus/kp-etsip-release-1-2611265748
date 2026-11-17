/** Fetch dashboard metrics using the shared authenticated API client. */
import { api } from '../../shared/api';
import type { ExecutiveDashboard, User } from '../../types';

/** Resolve the available landing destination without bypassing view permission. */
export function landingPath(user: User): string {
  if (user.mustChangePassword) return '/profile';
  if (!user.permissions.includes('view')) return '/account';
  const landing = user.defaultLandingPage || (['Administrator', 'Executive'].includes(user.role) ? 'dashboard' : 'applications');
  return `/${landing}`;
}

/** Load the matching scoped dashboard from the backend. */
export function getDashboard(query: string): Promise<ExecutiveDashboard> {
  return api<ExecutiveDashboard>(`/dashboard/executive${query ? `?${query}` : ''}`);
}
