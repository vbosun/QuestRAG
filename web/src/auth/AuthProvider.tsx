import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { sm2 } from "sm-crypto";
import { clearTokens, getAccessToken, setTokens } from "../request";

export interface UserInfo {
  id: number;
  full_name: string;
  id_number_masked: string;
  role: string;
}

interface AuthState {
  user: UserInfo | null;
  loading: boolean;
  encryptAndLogin: (idNumber: string, password: string) => Promise<void>;
  encryptAndLogout: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  encryptAndLogin: async () => {},
  encryptAndLogout: async () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

let cachedPublicKey: string | null = null;

async function getPublicKey(): Promise<string> {
  if (cachedPublicKey) return cachedPublicKey;
  const response = await fetch("/auth/public-key");
  if (!response.ok) throw new Error("获取公钥失败");
  const data = await response.json();
  cachedPublicKey = data.public_key;
  return cachedPublicKey!;
}

export function encryptWithSM2(plaintext: string): string {
  const pk = cachedPublicKey;
  if (!pk) throw new Error("公钥未加载");
  return sm2.doEncrypt(plaintext, pk, 0);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(() => {
    const stored = sessionStorage.getItem("user_info");
    return stored ? JSON.parse(stored) : null;
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function restore() {
      const token = getAccessToken();
      if (!token) {
        setLoading(false);
        return;
      }
      try {
        const response = await fetch("/auth/me", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) {
          clearTokens();
          setUser(null);
        } else {
          const data = await response.json();
          if (!cancelled) {
            setUser(data);
            sessionStorage.setItem("user_info", JSON.stringify(data));
          }
        }
      } catch {
        clearTokens();
        setUser(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    restore();
    return () => {
      cancelled = true;
    };
  }, []);

  const encryptAndLogin = useCallback(async (idNumber: string, password: string) => {
    if (!cachedPublicKey) {
      await getPublicKey();
    }

    const encryptedIdNumber = encryptWithSM2(idNumber);
    const encryptedPassword = encryptWithSM2(password);

    const response = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_number: encryptedIdNumber, password: encryptedPassword }),
    });

    const data = await response.json();

    if (!response.ok) {
      const detail = data.detail;
      throw new Error(detail?.message || "登录失败");
    }

    setTokens(data.access_token, data.refresh_token);
    setUser(data.user);
    sessionStorage.setItem("user_info", JSON.stringify(data.user));
  }, []);

  const encryptAndLogout = useCallback(async () => {
    try {
      await fetch("/auth/logout", {
        method: "POST",
        headers: { Authorization: `Bearer ${getAccessToken()}` },
      });
    } catch {
      // ignore logout errors
    }
    clearTokens();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, encryptAndLogin, encryptAndLogout }),
    [user, loading, encryptAndLogin, encryptAndLogout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
