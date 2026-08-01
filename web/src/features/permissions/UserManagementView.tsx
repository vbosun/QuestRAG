import { LockOutlined, UnlockOutlined, UserAddOutlined } from "@ant-design/icons";
import {
  App,
  Button,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { useEffect, useState } from "react";
import {
  createUser,
  disableUser,
  enableUser,
  kickUser,
  listRoles,
  listUsers,
  lockUser,
  resetUserPassword,
  unlockUser,
  updateUserRoles,
} from "../../api";
import type { RoleInfo, UserInfo, UserListResponse } from "./types";

const { Text } = Typography;

export function UserManagementView() {
  const { message } = App.useApp();
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<number | undefined>(undefined);
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const safeRoles = Array.isArray(roles) ? roles : [];
  const [createOpen, setCreateOpen] = useState(false);
  const [roleOpen, setRoleOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<UserInfo | null>(null);
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const [createForm] = Form.useForm();
  const [resetOpen, setResetOpen] = useState(false);
  const [resetPwd, setResetPwd] = useState("");

  async function refresh() {
    setLoading(true);
    try {
      const data: UserListResponse = await listUsers({
        search,
        role_code: roleFilter,
        status: statusFilter,
        page,
        page_size: 20,
      });
      setUsers(data.items);
      setTotal(data.total);
    } catch {
      message.error("加载用户列表失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, [page, search, roleFilter, statusFilter]);

  useEffect(() => {
    listRoles().then(setRoles).catch(() => {});
  }, []);

  async function handleCreate() {
    try {
      const values = await createForm.validateFields();
      await createUser(values);
      message.success("用户创建成功");
      setCreateOpen(false);
      createForm.resetFields();
      refresh();
    } catch {
      // validation error
    }
  }

  async function handleAssignRoles() {
    if (!selectedUser) return;
    try {
      await updateUserRoles(selectedUser.id, selectedRoles);
      message.success("角色分配成功");
      setRoleOpen(false);
      refresh();
    } catch {
      message.error("角色分配失败");
    }
  }

  async function handleResetPassword() {
    if (!selectedUser || !resetPwd) return;
    try {
      await resetUserPassword(selectedUser.id, resetPwd);
      message.success("密码已重置");
      setResetOpen(false);
      setResetPwd("");
    } catch {
      message.error("重置密码失败");
    }
  }

  function openRoleDialog(user: UserInfo) {
    setSelectedUser(user);
    setSelectedRoles(user.roles);
    setRoleOpen(true);
  }

  const columns = [
    { title: "姓名", dataIndex: "full_name", key: "full_name", width: 100 },
    { title: "身份证号", dataIndex: "id_number_masked", key: "id_number_masked", width: 180 },
    {
      title: "角色",
      dataIndex: "roles",
      key: "roles",
      render: (r: string[]) => r?.length ? r.map((c) => <Tag key={c}>{c}</Tag>) : <Tag>无</Tag>,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 80,
      render: (s: number) => s === 1 ? <Tag color="green">启用</Tag> : s === 0 ? <Tag color="red">禁用</Tag> : <Tag>锁定</Tag>,
    },
    {
      title: "锁定",
      dataIndex: "locked_until",
      key: "locked_until",
      width: 100,
      render: (v: string | null) => v ? <Tag color="red">已锁定</Tag> : <Text type="secondary">正常</Text>,
    },
    {
      title: "最后登录",
      dataIndex: "last_login_at",
      key: "last_login_at",
      width: 170,
      render: (v: string | null) => v ? new Date(v).toLocaleString() : "-",
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      key: "created_at",
      width: 170,
      render: (v: string) => new Date(v).toLocaleString(),
    },
    {
      title: "操作",
      key: "actions",
      width: 320,
      render: (_: unknown, record: UserInfo) => (
        <Space wrap>
          <Button size="small" onClick={() => openRoleDialog(record)}>分配角色</Button>
          <Button size="small" onClick={() => { setSelectedUser(record); setResetPwd(""); setResetOpen(true); }}>重置密码</Button>
          {record.locked_until ? (
            <Popconfirm title="确认解锁?" onConfirm={() => unlockUser(record.id).then(refresh)}>
              <Button size="small" icon={<UnlockOutlined />}>解锁</Button>
            </Popconfirm>
          ) : (
            <Popconfirm title="确认锁定?" onConfirm={() => lockUser(record.id).then(refresh)}>
              <Button size="small" icon={<LockOutlined />}>锁定</Button>
            </Popconfirm>
          )}
          {record.status === 1 ? (
            <Popconfirm title="确认禁用?" onConfirm={() => disableUser(record.id).then(refresh)}>
              <Button size="small" danger>禁用</Button>
            </Popconfirm>
          ) : (
            <Popconfirm title="确认启用?" onConfirm={() => enableUser(record.id).then(refresh)}>
              <Button size="small">启用</Button>
            </Popconfirm>
          )}
          <Popconfirm title="强制下线?" onConfirm={() => kickUser(record.id).then(refresh)}>
            <Button size="small" danger>下线</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Input.Search
          placeholder="搜索姓名/身份证"
          allowClear
          onSearch={setSearch}
          style={{ width: 220 }}
        />
        <Select
          placeholder="角色筛选"
          allowClear
          style={{ width: 140 }}
          onChange={(v: string | undefined) => setRoleFilter(v || "")}
          options={safeRoles.map((r) => ({ label: r.name, value: r.code }))}
        />
        <Select
          placeholder="状态筛选"
          allowClear
          style={{ width: 120 }}
          onChange={(v: number | undefined) => setStatusFilter(v)}
          options={[
            { label: "启用", value: 1 },
            { label: "禁用", value: 0 },
          ]}
        />
        <Button type="primary" icon={<UserAddOutlined />} onClick={() => setCreateOpen(true)}>
          新建用户
        </Button>
      </Space>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={users}
        loading={loading}
        pagination={{ current: page, total, pageSize: 20, onChange: setPage, showTotal: (t) => `共 ${t} 人` }}
      />

      <Modal title="新建用户" open={createOpen} onOk={handleCreate} onCancel={() => setCreateOpen(false)}>
        <Form form={createForm} layout="vertical">
          <Form.Item name="full_name" label="姓名" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="id_number" label="身份证号" rules={[{ required: true, min: 17, max: 18 }]}>
            <Input />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, min: 6 }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="role_codes" label="角色">
            <Select mode="multiple" placeholder="选择角色" options={safeRoles.map((r) => ({ label: r.name, value: r.code }))} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="分配角色" open={roleOpen} onOk={handleAssignRoles} onCancel={() => setRoleOpen(false)}>
        <Select
          mode="multiple"
          style={{ width: "100%" }}
          value={selectedRoles}
          onChange={setSelectedRoles}
          options={safeRoles.filter((r) => r.status === 1).map((r) => ({ label: `${r.name} (${r.code})`, value: r.code }))}
        />
      </Modal>

      <Modal title="重置密码" open={resetOpen} onOk={handleResetPassword} onCancel={() => setResetOpen(false)}>
        <Input.Password
          placeholder="输入新密码（至少6位）"
          value={resetPwd}
          onChange={(e) => setResetPwd(e.target.value)}
        />
      </Modal>
    </div>
  );
}
