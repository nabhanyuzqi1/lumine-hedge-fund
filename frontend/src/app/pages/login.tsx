import * as React from "react";
import { Navigate, useLocation, useSearchParams } from "react-router-dom";
import { useAuth } from "@/lib/auth/role-context";

/**
 * Halaman login Lumine — first-party internal auth.
 *
 * Credential diverifikasi backend (POST /api/auth/login, PBKDF2 hash di
 * PostgreSQL). Sukses → HttpOnly cookie `lumine_session` + redirect ke
 * halaman asal (?redirect= dari Caddy forward_auth 401, atau state.from
 * dari SPA route guard).
 */

export function LoginPage() {
  const { isAuthenticated, loading, login } = useAuth();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  const redirectTarget =
    searchParams.get("redirect") ??
    (location.state as { from?: Location })?.from?.pathname ??
    "/app/terminal";

  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-abyss">
        <div className="font-mono text-xs uppercase tracking-widest text-ink-faint">
          Verifying session…
        </div>
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to={redirectTarget} replace />;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username.trim(), password);
      // State update triggers the <Navigate> above.
    } catch {
      setError("Kredensial tidak valid. Hubungi administrator.");
    } finally {
      setSubmitting(false);
    }
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
            <span className="font-display text-lg font-semibold text-ink">LUMINE</span>
          </div>
          <p className="font-mono text-[11px] uppercase tracking-widest text-ink-faint">
            Institutional Trading Platform
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <label className="font-mono text-[11px] uppercase tracking-wider text-ink-faint">
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
              autoFocus
              className="w-full rounded-chip border border-line bg-raised px-3 py-2 font-mono text-sm text-ink placeholder-ink-faint outline-none ring-offset-0 focus:border-accent focus:ring-1 focus:ring-accent"
              placeholder="username"
            />
          </div>

          <div className="space-y-1">
            <label className="font-mono text-[11px] uppercase tracking-wider text-ink-faint">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              className="w-full rounded-chip border border-line bg-raised px-3 py-2 font-mono text-sm text-ink placeholder-ink-faint outline-none ring-offset-0 focus:border-accent focus:ring-1 focus:ring-accent"
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
            disabled={submitting}
            className="w-full rounded-chip bg-accent px-4 py-2.5 font-mono text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {submitting ? "Memverifikasi…" : "Masuk ke Platform"}
          </button>
        </form>

        <p className="text-center font-mono text-[10px] text-ink-faint">
          Akses terbatas untuk pengguna terdaftar
        </p>
      </div>
    </div>
  );
}
