let _permissions: string[] = [];

export function setPermissions(perms: string[]) {
  _permissions = perms;
}

export function hasPermission(code: string): boolean {
  return _permissions.includes(code);
}

export function hasAnyPermission(codes: string[]): boolean {
  return codes.some((c) => _permissions.includes(c));
}

export function hasAllPermissions(codes: string[]): boolean {
  return codes.every((c) => _permissions.includes(c));
}

type MenuItemLike = Record<string, unknown> & {
  permission?: string;
  ragScope?: string;
  children?: MenuItemLike[];
};

export function filterMenuByPermissions<T extends MenuItemLike>(
  items: T[],
  permissions: string[],
  ragScopes: string[] = [],
): T[] {
  return items
    .filter((item) => {
      if (item.permission && !permissions.includes(item.permission)) {
        return false;
      }
      if (item.ragScope && !ragScopes.includes(item.ragScope)) {
        return false;
      }
      return true;
    })
    .map((item) => {
      const { ragScope: _ragScope, ...safeItem } = item;
      if (item.children && item.children.length > 0) {
        return {
          ...safeItem,
          children: filterMenuByPermissions(item.children, permissions, ragScopes),
        } as T;
      }
      return safeItem as T;
    })
    .filter((item) => {
      if (item.children && item.children.length === 0) {
        return false;
      }
      return true;
    });
}
