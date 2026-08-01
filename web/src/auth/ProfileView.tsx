import { Button, Card, Descriptions, App } from "antd";
import { LogoutOutlined, KeyOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useAuth } from "./AuthProvider";

export function ProfileView() {
  const { user, encryptAndLogout } = useAuth();
  const navigate = useNavigate();
  const { message } = App.useApp();

  async function handleLogout() {
    await encryptAndLogout();
    message.success("已退出登录");
    navigate("/login", { replace: true });
  }

  if (!user) return null;

  return (
    <div style={{ maxWidth: 600 }}>
      <Card title="个人信息" style={{ marginBottom: 16 }}>
        <Descriptions column={1} size="small">
          <Descriptions.Item label="姓名">{user.full_name}</Descriptions.Item>
          <Descriptions.Item label="身份证号">{user.id_number_masked}</Descriptions.Item>
          <Descriptions.Item label="角色">
            {user.role === "ADMIN" ? "管理员" : user.role === "SYSTEM" ? "系统账号" : "普通用户"}
          </Descriptions.Item>
        </Descriptions>
      </Card>
      <div style={{ display: "flex", gap: 12 }}>
        <Button icon={<KeyOutlined />} onClick={() => navigate("/app/profile/password")}>
          修改密码
        </Button>
        <Button danger icon={<LogoutOutlined />} onClick={handleLogout}>
          退出登录
        </Button>
      </div>
    </div>
  );
}
