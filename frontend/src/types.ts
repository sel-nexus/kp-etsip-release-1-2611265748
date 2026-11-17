/** Define the safe identity contract shared by account and login views. */
export type RoleName = 'Administrator' | 'Executive' | 'Portfolio Leader' | 'Engineer' | 'Auditor' | 'Read Only';
export type Permission = 'view' | 'create' | 'edit' | 'delete' | 'export' | 'administer';
export interface User {
  id: string;
  name: string;
  email: string;
  role: RoleName;
  permissions: Permission[];
  portfolioAccess: string[];
  status: 'Active' | 'Inactive';
  lastLogin: string | null;
  authSource: 'local';
  managerName: string | null;
  vendorIndicator: boolean;
  defaultLandingPage: 'dashboard' | 'applications' | null;
  mustChangePassword: boolean;
  createdAt: string;
  updatedAt: string;
}
export interface LoginCredentials { email: string; password: string }
export interface LoginResponse { token: string; user: User }
