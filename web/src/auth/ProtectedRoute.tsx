import { Spin } from "antd";
import { Navigate } from "react-router-dom";
import { useAuth } from "./AuthProvider";

export function ProtectedRoute({
  children,
  permission,
  ragScope,
}: {
  children: React.ReactNode;
  permission?: string;
  ragScope?: string;
}) {
  const { user, loading, permissions, ragScopes } = useAuth();

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (permission && !permissions.includes(permission)) {
    return <Navigate to="/403" replace />;
  }

  if (ragScope && !ragScopes.includes(ragScope)) {
    return <Navigate to="/403" replace />;
  }

  return <>{children}</>;
}
