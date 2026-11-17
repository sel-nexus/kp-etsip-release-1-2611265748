/** Call only the three approved identity endpoints. */
import { api } from '../../shared/api';
import type { LoginCredentials, LoginResponse, User } from '../../types';
/** Establish a signed session using strict JSON credentials. */
export function login(credentials: LoginCredentials): Promise<LoginResponse> {
  return api('/auth/login', { method: 'POST', body: JSON.stringify(credentials) });
}
/** Read live identity and permissions for the persisted session. */
export function me(): Promise<User> { return api('/auth/me'); }
/** Revoke all prior server tokens for the current account. */
export function logout(): Promise<void> { return api('/auth/logout', { method: 'POST' }); }
