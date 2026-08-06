import { PlusOutlined } from "@ant-design/icons";
import {
  App,
  Button,
  Checkbox,
  Drawer,
  Form,
  Input,
  Modal,
  Popconfirm,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import { useEffect, useState } from "react";
import {
  createRole,
  deleteRole,
  getRole,
  listPermissionCatalog,
  listRoles,
  updateRole,
  updateRolePermissions,
  updateRoleRagScopes,
} from "../../api";
import type {
  PermissionCatalog,
  PermissionItem,
  RagScopeItem,
  RoleDetail,
  RoleInfo,
} from "./types";
import { GROUP_LABELS } from "./types";

export function RoleManagementView() {
  const { message } = App.useApp();
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [catalog, setCatalog] = useState<PermissionCatalog>({
    permissions: [],
    rag_scopes: [],
    permission_dependencies: {},
    rag_scope_dependencies: {},
    document_rag_scope_codes: [],
  });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingRole, setEditingRole] = useState<RoleDetail | null>(null);
  const [checkedPerms, setCheckedPerms] = useState<string[]>([]);
  const [checkedScopes, setCheckedScopes] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();

  async function refresh() {
    setLoading(true);
    try {
      setRoles(await listRoles());
    } catch {
      message.error("加载角色列表失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    listPermissionCatalog().then(setCatalog).catch(() => {});
  }, []);

  async function openDrawer(role: RoleInfo) {
    try {
      const detail: RoleDetail = await getRole(role.id);
      setEditingRole(detail);
      setCheckedPerms(detail.permissions.map((p) => p.code));
      setCheckedScopes(detail.rag_scopes.map((s) => s.code));
      setDrawerOpen(true);
    } catch {
      message.error("加载角色详情失败");
    }
  }

  async function handleSave() {
    if (!editingRole) return;
    setSaving(true);
    try {
      const normalizedPerms = normalizePermissionSelection(checkedPerms);
      await updateRolePermissions(editingRole.id, normalizedPerms);
      await updateRoleRagScopes(editingRole.id, normalizeScopeSelection(checkedScopes, normalizedPerms));
      if (editForm.isFieldsTouched()) {
        const values = await editForm.validateFields();
        await updateRole(editingRole.id, {
          ...values,
          status: values.status ? 1 : 0,
        });
      }
      message.success("保存成功");
      setDrawerOpen(false);
      refresh();
    } catch {
      message.error("保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleCreate() {
    try {
      const values = await createForm.validateFields();
      await createRole(values);
      message.success("角色创建成功");
      setCreateOpen(false);
      createForm.resetFields();
      refresh();
    } catch {
      // validation
    }
  }

  async function handleDelete(role: RoleInfo) {
    try {
      await deleteRole(role.id);
      message.success("角色已删除");
      refresh();
    } catch {
      message.error("删除失败");
    }
  }

  const groupedPerms = catalog.permissions.reduce<Record<string, PermissionItem[]>>((acc, p) => {
    const g = p.group_code || "other";
    (acc[g] ||= []).push(p);
    return acc;
  }, {});

  const permissionByCode = catalog.permissions.reduce<Record<string, PermissionItem>>((acc, item) => {
    acc[item.code] = item;
    return acc;
  }, {});
  const permissionDependencies = catalog.permission_dependencies || {};
  const childPermissionCodes = new Set(Object.keys(permissionDependencies));
  const scopeDependencies = catalog.rag_scope_dependencies || {};
  const documentScopeCodes = new Set(catalog.document_rag_scope_codes || []);
  const documentScopes = catalog.rag_scopes.filter((scope) => documentScopeCodes.has(scope.code));
  const toolDataScopes = catalog.rag_scopes.filter((scope) => !documentScopeCodes.has(scope.code));

  const permissionSections = [
    {
      group: "workspace",
      title: "页面入口与页面操作",
      description: "先授予页面入口，下面的按钮、接口和操作权限才会启用。",
    },
    {
      group: "llm_tool",
      title: "大模型工具调用权限",
      description: "工具权限决定 Agent 能调用哪些工具；工具涉及的数据范围在下方单独配置。",
    },
  ];

  const hierarchicalGroups = new Set([
    "workspace",
    "knowledge",
    "evaluation",
    "system",
    "permission",
    "public_services",
    "llm_tool",
  ]);
  const standaloneGroups = Object.keys(groupedPerms).filter((group) => !hierarchicalGroups.has(group));

  const riskMeta: Record<string, { label: string; color: string }> = {
    LOW: { label: "低", color: "green" },
    MEDIUM: { label: "中", color: "orange" },
    HIGH: { label: "高", color: "red" },
    CRITICAL: { label: "关键", color: "magenta" },
  };

  const columns = [
    { title: "角色名称", dataIndex: "name", key: "name", width: 140 },
    { title: "编码", dataIndex: "code", key: "code", width: 120 },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 80,
      render: (s: number) => s === 1 ? <Tag color="green">启用</Tag> : <Tag color="red">停用</Tag>,
    },
    { title: "用户数", dataIndex: "user_count", key: "user_count", width: 80 },
    { title: "权限数", dataIndex: "permission_count", key: "permission_count", width: 80 },
    { title: "检索范围数", dataIndex: "scope_count", key: "scope_count", width: 100 },
    {
      title: "内置",
      dataIndex: "system_builtin",
      key: "system_builtin",
      width: 80,
      render: (b: boolean) => b ? <Tag>Built-in</Tag> : null,
    },
    {
      title: "操作",
      key: "actions",
      width: 160,
      render: (_: unknown, record: RoleInfo) => (
        <Space>
          <Button size="small" onClick={() => openDrawer(record)}>编辑</Button>
          {!record.system_builtin && (
            <Popconfirm title="确认删除?" onConfirm={() => handleDelete(record)}>
              <Button size="small" danger>删除</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  function normalizePermissionSelection(values: string[]) {
    const selected = new Set(values);
    return values.filter((code) => {
      const parent = permissionDependencies[code];
      return !parent || selected.has(parent);
    });
  }

  function normalizeScopeSelection(values: string[], permissionValues = checkedPerms) {
    const selectedPerms = new Set(permissionValues);
    return values.filter((code) => {
      const deps = scopeDependencies[code] || [];
      return !deps.length || deps.some((permission) => selectedPerms.has(permission));
    });
  }

  function togglePermission(code: string) {
    setCheckedPerms((prev) => {
      const checked = prev.includes(code);
      if (checked) {
        const next = prev.filter((item) => item !== code && permissionDependencies[item] !== code);
        setCheckedScopes((scopes) => normalizeScopeSelection(scopes, next));
        return next;
      }
      return [...prev, code];
    });
  }

  function toggleScope(code: string, checked: boolean) {
    setCheckedScopes((prev) => {
      const next = checked ? Array.from(new Set([...prev, code])) : prev.filter((item) => item !== code);
      return normalizeScopeSelection(next);
    });
  }

  function isPermissionDisabled(permission: PermissionItem) {
    const parent = permissionDependencies[permission.code];
    return Boolean(parent && !checkedPerms.includes(parent));
  }

  function isScopeDisabled(scope: RagScopeItem) {
    const deps = scopeDependencies[scope.code] || [];
    return Boolean(deps.length && !deps.some((permission) => checkedPerms.includes(permission)));
  }

  function renderPermissionOption(permission: PermissionItem, nested = false) {
    const checked = checkedPerms.includes(permission.code);
    const disabled = isPermissionDisabled(permission);
    return (
      <button
        type="button"
        key={permission.code}
        className={`permission-option ${checked ? "checked" : ""} ${nested ? "nested" : ""}`}
        disabled={disabled}
        onClick={() => togglePermission(permission.code)}
      >
        <span>{permission.name}</span>
        <Tag color={riskMeta[permission.risk_level]?.color || "default"} bordered={false}>
          {riskMeta[permission.risk_level]?.label || permission.risk_level}
        </Tag>
      </button>
    );
  }

  function renderPermissionTree(group: string) {
    const perms = groupedPerms[group] || [];
    const parents = perms.filter((permission) => !childPermissionCodes.has(permission.code));
    return (
      <div className="permission-tree">
        {parents.map((parent) => {
          const children = catalog.permissions.filter((permission) => permissionDependencies[permission.code] === parent.code);
          return (
            <section className="permission-tree-node" key={parent.code}>
              {renderPermissionOption(parent)}
              {children.length > 0 && (
                <div className="permission-child-grid">
                  {children.map((child) => renderPermissionOption(child, true))}
                </div>
              )}
            </section>
          );
        })}
      </div>
    );
  }

  function renderPermissionGroup(group: string) {
    const perms = groupedPerms[group] || [];
    if (!perms.length) return null;
    return (
      <section className="permission-group" key={group}>
        <div className="permission-group-title">{GROUP_LABELS[group] || group}</div>
        <div className="permission-option-grid">
          {perms.map((permission) => renderPermissionOption(permission))}
        </div>
      </section>
    );
  }

  function renderScopeList(scopes: RagScopeItem[]) {
    return (
      <Space wrap className="rag-scope-picker">
        {scopes.map((scope) => {
          const disabled = isScopeDisabled(scope);
          const deps = scopeDependencies[scope.code] || [];
          return (
            <Checkbox
              key={scope.code}
              checked={checkedScopes.includes(scope.code)}
              disabled={disabled}
              onChange={(e) => toggleScope(scope.code, e.target.checked)}
            >
              <span>{scope.name}</span>
              {disabled && deps.length > 0 && (
                <Typography.Text type="secondary"> 需先勾选{deps.map((code) => permissionByCode[code]?.name || code).join(" / ")}</Typography.Text>
              )}
            </Checkbox>
          );
        })}
      </Space>
    );
  }

  return (
    <section className="view-shell knowledge-view">
      <header className="panel-header">
        <div className="page-title-block">
          <Typography.Title level={3}>角色管理</Typography.Title>
          <Typography.Text type="secondary" className="page-subtitle">
            创建权限组角色，维护系统功能权限、大模型工具权限与 RAG 检索范围。
          </Typography.Text>
        </div>
        <Space wrap>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建角色
          </Button>
        </Space>
      </header>

      <main className="knowledge-table-page menu-table-page">
        <div className="knowledge-table">
          <Table
            rowKey="id"
            columns={columns}
            dataSource={roles}
            loading={loading}
            pagination={false}
          />
        </div>
      </main>

      <Drawer
        title={`编辑角色: ${editingRole?.name || ""}`}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={640}
        extra={
          <Button type="primary" loading={saving} onClick={handleSave}>保存</Button>
        }
      >
        {editingRole && (
          <>
            <Form form={editForm} layout="vertical" initialValues={{ name: editingRole.name, description: editingRole.description, status: editingRole.status === 1 }}>
              <Form.Item name="name" label="角色名称" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="description" label="描述">
                <Input.TextArea rows={2} />
              </Form.Item>
              <Form.Item name="status" label="启用" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Form>

            <Typography.Title level={5} style={{ marginTop: 16 }}>系统功能权限 & 大模型工具权限</Typography.Title>
            <div className="permission-picker">
              {permissionSections.map((section) => (
                <section className="permission-group" key={section.group}>
                  <div className="permission-group-title">{section.title}</div>
                  <Typography.Text type="secondary">{section.description}</Typography.Text>
                  {renderPermissionTree(section.group)}
                </section>
              ))}
              {standaloneGroups.map((group) => renderPermissionGroup(group))}
            </div>

            <Typography.Title level={5} style={{ marginTop: 24 }}>知识库文档范围</Typography.Title>
            <Typography.Text type="secondary">这些范围只控制知识库文档检索；需先勾选“大模型工具调用权限”里的知识库检索工具。</Typography.Text>
            {renderScopeList(documentScopes)}

            <Typography.Title level={5} style={{ marginTop: 24 }}>工具数据范围</Typography.Title>
            <Typography.Text type="secondary">岗位库、模拟社保库、补贴政策库属于工具数据源，不混入知识库文档范围。</Typography.Text>
            {renderScopeList(toolDataScopes)}
          </>
        )}
      </Drawer>

      <Modal title="新建角色" open={createOpen} onOk={handleCreate} onCancel={() => setCreateOpen(false)}>
        <Form form={createForm} layout="vertical">
          <Form.Item name="code" label="角色编码" rules={[{ required: true, min: 2, max: 64 }]}>
            <Input />
          </Form.Item>
          <Form.Item name="name" label="角色名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </section>
  );
}
