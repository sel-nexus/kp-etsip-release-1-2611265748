/** Define the safe identity contract shared by account and login views. */
export type RoleName = 'Administrator' | 'Executive' | 'Portfolio Leader' | 'Engineer' | 'Auditor' | 'Read Only';
export type Permission = 'view' | 'create' | 'edit' | 'delete' | 'export' | 'administer';
export interface Role { id: string; name: RoleName; description: string; permissions: Permission[]; createdAt: string; updatedAt: string }
export interface RoleWrite { description: string; permissions: Permission[] }
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
export interface UserWrite {
  name: string;
  email: string;
  role: RoleName;
  portfolioAccess: string[];
  status: 'Active' | 'Inactive';
  managerName: string | null;
  vendorIndicator: boolean;
  password?: string;
}

export type LandingPage = 'dashboard' | 'applications';
export interface ProfileUpdate { defaultLandingPage: LandingPage }
export interface PasswordChange { currentPassword: string; newPassword: string }

export interface ListPage<T> { items: T[]; total: number; page: number; pageSize: number }
export interface AuditRecord {
  id: string;
  timestamp: string;
  userId: string | null;
  userName: string;
  action: 'login' | 'create' | 'edit' | 'delete' | 'roleChange' | 'permissionChange' | 'export';
  entityType: string;
  entityId: string | null;
  details: string;
  createdAt: string;
  updatedAt: string;
}
export interface PortfolioWrite { name: string; owner: string; description: string; productArea: string; status: 'Active' | 'Archived' }
export interface Portfolio extends PortfolioWrite { id: string; applicationCount: number; qualityScore: number | null; createdAt: string; updatedAt: string }
export interface LinkedApplication { id: string; name: string; portfolioId: string; productArea: string; lifecycleStatus: 'Active' | 'Deprecated' | 'Retired'; qualityScore: number; riskLevel: 'Low' | 'Medium' | 'High' }
export interface Application extends LinkedApplication {
  description: string;
  portfolioName: string;
  businessOwner: string;
  technologyOwner: string;
  etsOwner: string;
  criticality: 'Low' | 'Medium' | 'High' | 'Critical';
  tier: number;
  technologyStack: string;
  repositoryLink: string | null;
  pipelineLink: string | null;
  applicationHealthScore: number;
  automationCoverage: number;
  unitTestCoverage: number;
  openDefects: number;
  openCriticalDefects: number;
  createdAt: string;
  updatedAt: string;
}
export type ApplicationWrite = Omit<Application, 'id' | 'portfolioName' | 'createdAt' | 'updatedAt'>;

export interface PortfolioMetric { id: string; name: string; applicationCount: number; qualityScore: number | null; highRiskCount: number }
export interface ExecutiveDashboard {
  enterpriseQualityScore: number | null;
  applicationHealthScore: number | null;
  automationMaturityScore: number | null;
  openCriticalDefects: number;
  applicationsAtRisk: number;
  totalApplications: number;
  totalPortfolios: number;
  portfolios: PortfolioMetric[];
}
