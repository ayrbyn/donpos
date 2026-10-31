import { useAuthStore } from "../store/auth";

const BASE_URL = (process.env.EXPO_PUBLIC_API_URL ?? "").replace(/\/+$/, "");
const TIMEOUT_MS = 15000;

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type Options = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  form?: Record<string, string>;
  auth?: boolean;
  outlet?: boolean;
};

function errorMessage(data: unknown, fallback: string): string {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string };
      if (first.msg) {
        return first.msg;
      }
    }
  }
  return fallback;
}

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const { method = "GET", body, form, auth = true, outlet = true } = options;
  const { token, outletId, logout } = useAuthStore.getState();

  const headers: Record<string, string> = { Accept: "application/json" };
  if (auth && token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (outlet && outletId) {
    headers["X-Outlet-ID"] = outletId;
  }

  let payload: string | undefined;
  if (form) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    payload = new URLSearchParams(form).toString();
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(BASE_URL + path, {
      method,
      headers,
      body: payload,
      signal: controller.signal,
    });
  } catch {
    throw new ApiError(
      0,
      "Tidak dapat terhubung ke server. Periksa jaringan dan alamat server."
    );
  } finally {
    clearTimeout(timer);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    if (response.status === 401 && auth) {
      logout();
    }
    throw new ApiError(
      response.status,
      errorMessage(data, "Permintaan gagal (" + response.status + ")")
    );
  }

  return data as T;
}