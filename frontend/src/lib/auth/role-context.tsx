/**
 * Role-based auth context untuk Lumine.
 *
 * Role hierarchy:
 *   guest       → hanya bisa lihat landing page
 *   user        → akses /app/* (terminal, dashboard, journal, dll)
 *   admin       → akses /app/* + /admin/* (API keys, settings)
 *   superadmin  → akses semua termasuk /superadmin (control center)
 *
 * Implementasi: session cookie dari Authelia (untuk superadmin/admin)
 * atau API key scope (untuk user level dari API).
 *
 * Untuk MVP: role disimpan di localStorage setelah user login.
 * Production: integrate dengan Authelia session + backend session.
 */
import * as React from "react";
import { Navigate, useLocation } from "react-router-dom";

export type UserRole = "guest" | "user" | "admin" | "superadmin";

interface AuthState {
  role: UserRole;
  username: string | null;
  isAuthenticated: boolean;
}

interface AuthContextValue extends AuthState {
  login: (role: UserRole, username: string) => void;
  logout: () => void;
  hasRole: (required: UserRole) => boolean;
}

const ROLE_HIERARCHY: Record<UserRole, number> = {
  guest: 0,
  user: 1,
  admin: 2,
  superadmin: 3,
};

const AUTH_STORAGE_KEY = "lumine_auth";

function loadAuthState(): AuthState {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<AuthState>;
      if (parsed.role && parsed.username) {
        return {
          role: parsed.role,
          username: parsed.username,
          isAuthenticated: true,
        };
      }
    }
  } catch {
    // ignore
  }
  return { role: "guest", username: null, isAuthenticated: false };
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<AuthState>(loadAuthState);

  const login = React.useCallback((role: UserRole, username: string) => {
    const next: AuthState = { role, username, isAuthenticated: true };
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(next));
    setState(next);
  }, []);

  const logout = React.useCallback(() => {
    localStorage.removeItem(AUTH_STORAGE_KEY);
    setState({ role: "guest", username: null, isAuthenticated: false });
  }, []);

  const hasRole = React.useCallback(
    (required: UserRole) => ROLE_HIERARCHY[state.role] >= ROLE_HIERARCHY[required],
    [state.role]
  );

  return (
    <AuthContext.Provider value={{ ...state, login, logout, hasRole }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

/** Redirect ke /login jika role tidak cukup. */
export function RequireRole({
  role,
  children,
  redirectTo = "/login",
}: {
  role: UserRole;
  children: React.ReactNode;
  redirectTo?: string;
}) {
  const { hasRole } = useAuth();
  const location = useLocation();

  if (!hasRole(role)) {
    return <Navigate to={redirectTo} state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
