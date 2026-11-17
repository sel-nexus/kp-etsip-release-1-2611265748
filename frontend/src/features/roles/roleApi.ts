/** Read and update fixed role records through the shared bearer client. */
import { api } from '../../shared/api';
import type { ListPage, Role, RoleWrite } from '../../types';

/** Read the bounded set of fixed roles. */
export function listRoles(): Promise<ListPage<Role>> {
  return api<ListPage<Role>>('/roles?page=1&pageSize=100');
}

/** Persist a role's description and generic permissions. */
export function saveRole(id: string, data: RoleWrite): Promise<Role> {
  return api<Role>(`/roles/${id}`, { method: 'PUT', body: JSON.stringify(data) });
}
