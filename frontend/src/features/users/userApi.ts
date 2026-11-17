/** Consume the account administration API with the shared bearer client. */
import { api, ApiError } from '../../shared/api';
import type { ListPage, User, UserWrite } from '../../types';

/** Apply the fixed role and live generic permission boundary. */
export function canAdminister(user: User | null): boolean {
  return Boolean(user && !user.mustChangePassword && user.status === 'Active' && user.role === 'Administrator' && user.permissions.includes('administer'));
}
/** Translate generic validation wording for the account form. */
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  try { return await api<T>(path, options); }
  catch (error) {
    if (error instanceof ApiError && error.status === 422) throw new ApiError(422, 'Check the user fields and assignments.');
    throw error;
  }
}
/** Fetch a bounded, filtered account page. */
export function listUsers(query: string): Promise<ListPage<User>> { return request(`/users?${query}`); }
/** Persist a complete account write. */
export function saveUser(value: UserWrite, id?: string): Promise<User> {
  return request(id ? `/users/${encodeURIComponent(id)}` : '/users', { method: id ? 'PUT' : 'POST', body: JSON.stringify(value) });
}
/** Deactivate while retaining audit references. */
export function deactivateUser(id: string): Promise<void> {
  return request(`/users/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
