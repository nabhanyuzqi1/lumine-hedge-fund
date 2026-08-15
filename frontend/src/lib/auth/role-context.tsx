/**
 * Role-based auth context untuk Lumine — backend session (internal auth).
 *
 * Role hierarchy:
 *   guest       → hanya bisa lihat landing page
 *   user        → akses /app/* (terminal, dashboard, journal, dll)
 *   admin       → akses /app/* + /admin/* (API keys, settings)
 *   superadmin  → akses semua termasuk /superadmin (control center)
 *
 * Sesi adalah HttpOnly cookie (`lumine_session`) dari backend
 * (backend/src/lumine/api/routers/auth.py) — tidak ada localStorage,
 * tidak ada Authelia/Keycloak. Role di-verifikasi server-side via
 * /api/auth/me saat mount dan /api/auth/verify untuk gate berlapis.
 */
import * as React from "react";
import { Navigate, useLocation } from "react-router-dom";

import { fetchMe, login as apiLogin, logout as apiLogout } from "@/lib/api/session";

export type UserRole = "guest" | "user" | "admin" | "superadmin";

interface AuthState {
  role: UserRole;
  username: string | null;
  isAuthenticated: boolean;
}

interface AuthContextValue extends AuthState {
  /** True while the initial /api/auth/me check is in flight. */
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (required: UserRole) => boolean;
}

const ROLE_HIERARCHY: Record<UserRole, number> = {
  guest: 0,
  user: 1,
  admin: 2,
  superadmin: 3,
};

const GUEST_STATE: AuthState = {
  role: "guest",
  username: null,
  isAuthenticated: false,
};

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<AuthState>(GUEST_STATE);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    let cancelled = false;
    fetchMe()
      .then((user) => {
        if (!cancelled) {
          setState({ role: user.role, username: user.username, isAuthenticated: true });
        }
      })
      .catch(() => {
        // 401 / network error → guest. Never crash the app shell.
        if (!cancelled) {
          setState(GUEST_STATE);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = React.useCallback(async (username: string, password: string) => {
    const user = await apiLogin(username, password);
    setState({ role: user.role, username: user.username, isAuthenticated: true });
  }, []);

  const logout = React.useCallback(async () => {
    try {
      await apiLogout();
    } catch {
      // Best effort — clear local state regardless of network outcome.
    }
    setState(GUEST_STATE);
  }, []);

  const hasRole = React.useCallback(
    (required: UserRole) => ROLE_HIERARCHY[state.role] >= ROLE_HIERARCHY[required],
    [state.role]
  );

  const value = React.useMemo<AuthContextValue>(
    () => ({ ...state, loading, login, logout, hasRole }),
    [state, loading, login, logout, hasRole]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

/**
 * Route guard — menunggu verifikasi session awal (loading) sebelum
 * memutuskan redirect, sehingga refresh halaman tidak mem-flash /login.
 */
export function RequireRole({
  role,
  children,
  redirectTo = "/login",
}: {
  role: UserRole;
  children: React.ReactNode;
  redirectTo?: string;
}) {
  const { hasRole, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-abyss">
        <div className="font-mono text-xs uppercase tracking-widest text-ink-faint">
          Verifying session…
        </div>
      </div>
    );
  }

  if (!hasRole(role)) {
    return <Navigate to={redirectTo} state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
