import { Button, Card, Form, Input, Typography, App } from "antd";
import { LockOutlined, IdcardOutlined } from "@ant-design/icons";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "./AuthProvider";

const { Title, Text } = Typography;

export function LoginPage() {
  const [loading, setLoading] = useState(false);
  const { encryptAndLogin } = useAuth();
  const navigate = useNavigate();
  const { message } = App.useApp();

  async function handleSubmit(values: { id_number: string; password: string }) {
    setLoading(true);
    try {
      await encryptAndLogin(values.id_number, values.password);
      navigate("/app/chat", { replace: true });
    } catch (err) {
      message.error(err instanceof Error ? err.message : "登录失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <Card className="login-card">
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <div className="brand-mark" style={{ margin: "0 auto 12px" }}>Q</div>
          <Title level={3}>QuestRAG</Title>
          <Text type="secondary">知识库问答工作台</Text>
        </div>
        <Form layout="vertical" onFinish={handleSubmit} size="large">
          <Form.Item
            name="id_number"
            rules={[
              { required: true, message: "请输入身份证号" },
              { pattern: /^\d{17}[\dXx]$/, message: "身份证号格式不正确" },
            ]}
          >
            <Input prefix={<IdcardOutlined />} placeholder="身份证号" maxLength={18} />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[{ required: true, message: "请输入密码" }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
