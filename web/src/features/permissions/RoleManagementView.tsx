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
  const [catalog, setCatalog] = useState<PermissionCatalog>({ permissions: [], rag_scopes: [] });
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
      await updateRolePermissions(editingRole.id, checkedPerms);
      await updateRoleRagScopes(editingRole.id, checkedScopes);
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

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          新建角色
        </Button>
      </Space>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={roles}
        loading={loading}
        pagination={false}
      />

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
              {Object.entries(groupedPerms).map(([group, perms]) => (
                <section className="permission-group" key={group}>
                  <div className="permission-group-title">{GROUP_LABELS[group] || group}</div>
                  <div className="permission-option-grid">
                    {perms.map((p) => {
                      const checked = checkedPerms.includes(p.code);
                      return (
                        <button
                          type="button"
                          key={p.code}
                          className={`permission-option ${checked ? "checked" : ""}`}
                          onClick={() => {
                            setCheckedPerms((prev) =>
                              checked ? prev.filter((c) => c !== p.code) : [...prev, p.code],
                            );
                          }}
                        >
                          <span>{p.name}</span>
                          <Tag color={riskMeta[p.risk_level]?.color || "default"} bordered={false}>
                            {riskMeta[p.risk_level]?.label || p.risk_level}
                          </Tag>
                        </button>
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>

            <Typography.Title level={5} style={{ marginTop: 24 }}>RAG 检索范围</Typography.Title>
            <Space wrap className="rag-scope-picker">
              {catalog.rag_scopes.map((s) => (
                <Checkbox
                  key={s.code}
                  checked={checkedScopes.includes(s.code)}
                  onChange={(e) => {
                    setCheckedScopes((prev) =>
                      e.target.checked ? [...prev, s.code] : prev.filter((c) => c !== s.code),
                    );
                  }}
                >
                  {s.name}
                </Checkbox>
              ))}
            </Space>
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
    </div>
  );
}
