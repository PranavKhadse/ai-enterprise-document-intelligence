/**
 * Phase 10 Authentication, Roles, Departments, and RBAC Context Types.
 */

export interface RoleResponse {
  id: string;
  name: string;
  description?: string | null;
}

export interface DepartmentResponse {
  id: string;
  name: string;
  description?: string | null;
}

export interface UserResponse {
  id: string;
  email: string;
  is_active: boolean;
  department_id?: string | null;
  department?: DepartmentResponse | null;
  roles: string[];
  clearance_level: number; // 1 to 4
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserResponse;
}

export interface UserLoginRequest {
  email: string;
  password: string;
}

export interface UserRegisterRequest {
  email: string;
  password: string;
  department_id?: string | null;
  role_names?: string[];
}

export interface RBACContext {
  user_id: string;
  email: string;
  roles: string[];
  department_id?: string | null;
  clearance_level: number;
  is_admin: boolean;
  token_version: number;
}
