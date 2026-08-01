import { redirect } from "next/navigation";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    public readonly fields?: Record<string, string[]>,
    public readonly retryAfterSeconds?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiResponse<T> {
  data?: T;
  detail: string;
  code: string;
  status: number;
  fields?: Record<string, string[]>;
  retry_after_seconds?: number;
}

/** Lazily fetch the session-bound CSRF token and cache it in sessionStorage. */
async function fetchCsrfToken(): Promise<string | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/sessions/csrf`, {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) return null;
    const body = (await res.json().catch(() => null)) as ApiResponse<{ csrf_token: string }> | null;
    return body?.data?.csrf_token ?? null;
  } catch {
    return null;
  }
}

function redirectOnAuth(code?: string): void {
  if (typeof window !== "undefined") {
    // No session at all → send to sign-in. Genuine expiry → dedicated screen.
    window.location.assign(code === "session_expired" ? "/auth/expired" : "/login");
  }
}

/** Client-side fetch wrapper with error normalization. */
export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit & { csrf?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };

  if (options.csrf) {
    // CSRF token is session-bound, fetched lazily via /sessions/csrf.
    let token = sessionStorage.getItem("gp_csrf");
    if (!token) {
      token = await fetchCsrfToken();
      if (token) sessionStorage.setItem("gp_csrf", token);
    }
    if (token) headers["X-CSRF-Token"] = token;
  }

  const doFetch = async (): Promise<{ res: Response; body: ApiResponse<T> | null }> => {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      credentials: "include",
      headers,
    });
    const body = (await res.json().catch(() => null)) as ApiResponse<T> | null;
    return { res, body };
  };

  let { res, body } = await doFetch();

  // A session rotated by a concurrent request, or a stale CSRF token, can surface
  // as a single 401 even while the user is still authenticated. Refresh the
  // session-bound CSRF token (which also re-validates the session cookie) and
  // retry once so a transient response doesn't boot the user to the login page.
  if (res.status === 401) {
    sessionStorage.removeItem("gp_csrf");
    const token = await fetchCsrfToken();
    if (token) {
      sessionStorage.setItem("gp_csrf", token);
      if (options.csrf) headers["X-CSRF-Token"] = token;
      ({ res, body } = await doFetch());
    }
  }

  if (res.status === 401) {
    redirectOnAuth(body?.code);
    throw new ApiError(
      body?.detail ?? "Authentication required",
      res.status,
      body?.code ?? "unauthorized",
    );
  }

  if (!res.ok) {
    throw new ApiError(
      body?.detail ?? "Request failed",
      res.status,
      body?.code ?? "error",
      body?.fields,
      body?.retry_after_seconds,
    );
  }

  return body as T;
}

/** Server-side helper for redirects when unauthenticated. */
export function requireAuth(hasSession: boolean) {
  if (!hasSession) redirect("/login");
}
