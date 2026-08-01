import { Button, Card, Form, Input, App } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth, encryptWithSM2, ensurePublicKey } from "./AuthProvider";

export function ChangePasswordView() {
  const [loading, setLoading] = useState(false);
  const { encryptAndLogout } = useAuth();
  const navigate = useNavigate();
  const { message } = App.useApp();

  async function handleSubmit(values: { old_password: string; new_password: string; confirm_password: string }) {
    if (values.new_password !== values.confirm_password) {
      message.error("两次输入的新密码不一致");
      return;
    }
    if (values.new_password.length < 8) {
      message.error("密码长度不能少于8位");
      return;
    }
    if (values.new_password === values.old_password) {
      message.error("新密码不能与旧密码相同");
      return;
    }

    setLoading(true);
    try {
      await ensurePublicKey();
      const token = sessionStorage.getItem("access_token");
      const response = await fetch("/auth/change-password", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          old_password: encryptWithSM2(values.old_password),
          new_password: encryptWithSM2(values.new_password),
          confirm_password: encryptWithSM2(values.confirm_password),
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail?.message || "修改密码失败");
      }
      message.success("密码已修改，请重新登录");
      await encryptAndLogout();
      navigate("/login", { replace: true });
    } catch (err) {
      message.error(err instanceof Error ? err.message : "修改密码失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 480 }}>
      <Card title="修改密码">
        <Form layout="vertical" onFinish={handleSubmit} size="large">
          <Form.Item
            name="old_password"
            rules={[{ required: true, message: "请输入旧密码" }]}
          >
            <Input.Password placeholder="旧密码" />
          </Form.Item>
          <Form.Item
            name="new_password"
            rules={[
              { required: true, message: "请输入新密码" },
              { min: 8, message: "密码长度不能少于8位" },
            ]}
          >
            <Input.Password placeholder="新密码" />
          </Form.Item>
          <Form.Item
            name="confirm_password"
            rules={[
              { required: true, message: "请确认新密码" },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue("new_password") === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error("两次输入的新密码不一致"));
                },
              }),
            ]}
          >
            <Input.Password placeholder="确认新密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              修改密码
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
