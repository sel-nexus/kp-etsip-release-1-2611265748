/** Consume the exact portfolio API through the existing bearer boundary. */
import { api, ApiError } from '../../shared/api';
import type { LinkedApplication, ListPage, Portfolio, PortfolioWrite, User, Permission } from '../../types';
/** Apply immutable portfolio role rules in addition to current generic permissions. */
export function canPortfolio(user: User | null, permission: Permission, id?: string): boolean {
  if (!user || user.mustChangePassword || !user.permissions.includes('view') || !user.permissions.includes(permission)) return false;
  const scoped = user.portfolioAccess.length > 0 || !['Administrator', 'Executive', 'Auditor'].includes(user.role);
  if (id && scoped && !user.portfolioAccess.includes(id)) return false;
  if (permission === 'create') return user.role === 'Administrator' && !scoped;
  if (permission === 'delete') return user.role === 'Administrator';
  if (permission === 'edit') return user.role === 'Administrator' || (user.role === 'Portfolio Leader' && Boolean(id) && user.portfolioAccess.includes(id!));
  return permission === 'view';
}
/** Replace auth-specific validation wording only for this feature's invalid payloads. */
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  try { return await api<T>(path, options); } catch (failure) {
    if (failure instanceof ApiError && failure.status === 422) throw new ApiError(422, 'Check the portfolio fields and filters.');
    throw failure;
  }
}
/** Fetch the URL-selected portfolio inventory. */
export function listPortfolios(query: string): Promise<ListPage<Portfolio>> {
  return request(`/portfolios?${query}`);
}
/** Fetch a single visible portfolio and its derived metrics. */
export function getPortfolio(id: string): Promise<Portfolio> { return request(`/portfolios/${encodeURIComponent(id)}`); }
/** Read actual linked inventory without inventing application records. */
export function linkedApplications(id: string, page: number): Promise<ListPage<LinkedApplication>> {
  return request(`/portfolios/${encodeURIComponent(id)}/applications?page=${page}&pageSize=25`);
}
/** Persist a new portfolio or replace maintained fields on an existing one. */
export function savePortfolio(payload: PortfolioWrite, id?: string): Promise<Portfolio> {
  return request(id ? `/portfolios/${encodeURIComponent(id)}` : '/portfolios', { method: id ? 'PUT' : 'POST', body: JSON.stringify(payload) });
}
/** Request reference-safe Administrator deletion. */
export function deletePortfolio(id: string): Promise<void> {
  return request(`/portfolios/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
