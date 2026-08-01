let accessToken: string | null = sessionStorage.getItem("access_token");
let refreshToken: string | null = sessionStorage.getItem("refresh_token");
let refreshPromise: Promise<boolean> | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function setTokens(access: string, refresh: string) {
  accessToken = access;
  refreshToken = refresh;
  sessionStorage.setItem("access_token", access);
  sessionStorage.setItem("refresh_token", refresh);
}

export function clearTokens() {
  accessToken = null;
  refreshToken = null;
  sessionStorage.removeItem("access_token");
  sessionStorage.removeItem("refresh_token");
  sessionStorage.removeItem("user_info");
}

async function refreshAccessTokenOnce(): Promise<boolean> {
  if (!refreshToken) return false;

  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = (async () => {
    try {
      const response = await fetch("/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) return false;

      const data = await response.json();
      accessToken = data.access_token;
      sessionStorage.setItem("access_token", data.access_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

interface RequestOptions extends Omit<RequestInit, "headers"> {
  headers?: Record<string, string>;
}

export async function request(path: string, options: RequestOptions = {}): Promise<Response> {
  const headers: Record<string, string> = { ...options.headers };

  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }

  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }

  let response = await fetch(path, { ...options, headers });

  if (response.status !== 401) return response;

  const refreshed = await refreshAccessTokenOnce();
  if (!refreshed) {
    clearTokens();
    window.location.hash = "";
    window.location.pathname = "/login";
    throw new Error("登录已失效，请重新登录");
  }

  headers["Authorization"] = `Bearer ${accessToken}`;
  return fetch(path, { ...options, headers });
}

export async function requestJson<T = unknown>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await request(path, options);
  const text = await response.text();
  let data: unknown = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }
  if (!response.ok) {
    const detail = (data as { detail?: { message?: string } | string })?.detail;
    const message =
      detail && typeof detail === "object" && "message" in detail
        ? detail.message
        : typeof detail === "string"
          ? detail
          : "请求失败";
    throw new Error(message);
  }
  return data as T;
}
