export interface PermissionItem {
  code: string;
  name: string;
  type: string;
  group_code: string;
  risk_level: string;
  description?: string;
}

export interface RagScopeItem {
  code: string;
  name: string;
  description?: string;
}

export interface PermissionCatalog {
  permissions: PermissionItem[];
  rag_scopes: RagScopeItem[];
}

export interface RoleInfo {
  id: number;
  code: string;
  name: string;
  description: string;
  status: number;
  system_builtin: boolean;
  user_count: number;
  permission_count: number;
  scope_count: number;
  created_at: string;
  updated_at: string;
}

export interface RoleDetail extends RoleInfo {
  permissions: PermissionItem[];
  rag_scopes: RagScopeItem[];
}

export interface UserInfo {
  id: number;
  full_name: string;
  id_number_masked: string;
  status: number;
  roles: string[];
  locked_until: string | null;
  last_login_at: string | null;
  last_login_ip: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserListResponse {
  items: UserInfo[];
  total: number;
  page: number;
  page_size: number;
}

export const GROUP_LABELS: Record<string, string> = {
  workspace: "工作台页面",
  knowledge: "知识库操作",
  evaluation: "评测操作",
  system: "系统配置",
  permission: "权限管理",
  llm_tool: "大模型工具",
};

export const RISK_COLORS: Record<string, string> = {
  LOW: "green",
  MEDIUM: "orange",
  HIGH: "red",
  CRITICAL: "magenta",
};
