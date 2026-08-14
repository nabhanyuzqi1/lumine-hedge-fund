import * as React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth/role-context";

/**
 * Halaman login sederhana untuk Lumine.
 * Production: integrate dengan Authelia SSO atau backend session.
 * MVP: simple credential entry yang set role ke localStorage.
 */

// Demo credentials — replace dengan real auth di production
const DEMO_CREDENTIALS: Record<string, { password: string; role: "user" | "admin" | "superadmin" }> = {
  trader: { password: "lumine2026", role: "user" },
  admin: { password: "lumine-admin", role: "admin" },
};

export function LoginPage() {
  const { isAuthenticated, login } = useAuth();
  const location = useLocation();
  const from = (location.state as { from?: Location })?.from?.pathname ?? "/app/terminal";

  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  if (isAuthenticated) {
    return <Navigate to={from} replace />;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    await new Promise((r) => setTimeout(r, 300));

    const cred = DEMO_CREDENTIALS[username.toLowerCase()];
    if (cred && cred.password === password) {
      login(cred.role, username);
    } else {
      setError("Kredensial tidak valid. Hubungi administrator.");
    }
    setLoading(false);
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-abyss">
      <div className="w-full max-w-sm space-y-6 p-8">
        {/* Logo */}
        <div className="space-y-1 text-center">
          <div className="flex items-center justify-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-chip bg-accent">
              <span className="font-display text-sm font-bold text-white">L</span>
            </div>
            <span className="font-display text-lg font-semibold text-text-primary">LUMINE</span>
          </div>
          <p className="font-mono text-[11px] uppercase tracking-widest text-text-muted">
            Institutional Trading Platform
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <label className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
              className="w-full rounded-chip border border-border-subtle bg-bg-raised px-3 py-2 font-mono text-sm text-text-primary placeholder-text-muted outline-none ring-offset-0 focus:border-accent focus:ring-1 focus:ring-accent"
              placeholder="username"
            />
          </div>

          <div className="space-y-1">
            <label className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              className="w-full rounded-chip border border-border-subtle bg-bg-raised px-3 py-2 font-mono text-sm text-text-primary placeholder-text-muted outline-none focus:border-accent focus:ring-1 focus:ring-accent"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <p className="rounded-chip bg-down/10 px-3 py-2 font-mono text-xs text-down">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-chip bg-accent px-4 py-2.5 font-mono text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "Verifikasi…" : "Masuk ke Platform"}
          </button>
        </form>

        <p className="text-center font-mono text-[10px] text-text-muted">
          Akses terbatas untuk pengguna terdaftar
        </p>
      </div>
    </div>
  );
}
