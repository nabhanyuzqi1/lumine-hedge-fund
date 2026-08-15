// Copyright (c) 2026 Lumine. All rights reserved.
/**
 * First-party session auth API (replaces Authelia/Keycloak SSO).
 *
 * Backend: backend/src/lumine/api/routers/auth.py (mounted at /api/auth).
 * The session is an HttpOnly cookie (`lumine_session`, HMAC-SHA256 signed),
 * so these calls use plain `fetch` with `credentials: "include"` — no HMAC
 * headers, no localStorage tokens.
 */

export interface SessionUser {
  username: string;
  role: "user" | "admin" | "superadmin";
}

export interface Envelope<T> {
  data: T;
  meta: { request_id: string; status: string; timestamp: string };
}

const SESSION_BASE = "/api/auth";

async function sessionFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${SESSION_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  const body = (await res.json().catch(() => null)) as Envelope<T> | null;
  if (!res.ok) {
    throw new Error(
      (body as { error?: { message?: string } } | null)?.error?.message ??
        `request failed (${res.status})`
    );
  }
  if (!body) {
    throw new Error("empty response");
  }
  return body.data;
}

/** POST /api/auth/login — sets the session cookie. */
export async function login(
  username: string,
  password: string
): Promise<SessionUser> {
  return sessionFetch<SessionUser>("/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

/** POST /api/auth/logout — clears the session cookie. */
export async function logout(): Promise<void> {
  await sessionFetch<{ ok: boolean }>("/logout", { method: "POST" });
}

/** GET /api/auth/me — current session principal (throws on 401). */
export async function fetchMe(): Promise<SessionUser> {
  return sessionFetch<SessionUser>("/me");
}

/** GET /api/auth/verify — role-gated check used by guards. */
export async function verifySession(
  requiredRole: "user" | "admin" | "superadmin"
): Promise<SessionUser | null> {
  try {
    return await sessionFetch<SessionUser>(
      `/verify?role=${encodeURIComponent(requiredRole)}`
    );
  } catch {
    return null;
  }
}
